"""Progress database, spaced repetition, backup/restore, corruption handling and project files."""
import datetime as dt
import json

import pytest

from finpilot.core import hotel as H
from finpilot.data import projects as pj
from finpilot.data.db import Database


def test_settings_defaults_and_round_trip(db):
    assert db.get_setting("theme") == "light"
    assert db.get_setting("gamification") is True
    db.set_setting("theme", "dark")
    db.set_setting("daily_goal_xp", 40)
    assert db.get_setting("theme") == "dark" and db.get_setting("daily_goal_xp") == 40


def test_progress_persists_across_reopen(tmp_path):
    p = tmp_path / "p.db"
    d = Database(p)
    d.start_lesson("L1.1", "guided")
    d.save_step("L1.1", 4)
    d.complete_lesson("L1.1", 0.9)
    d.close()
    d2 = Database(p)
    pr = d2.lesson_progress("L1.1")
    assert pr["status"] == "completed" and pr["best_score"] == pytest.approx(0.9)
    d2.close()


def test_best_score_keeps_maximum(db):
    db.start_lesson("L1.1", "guided")
    db.complete_lesson("L1.1", 0.9)
    db.complete_lesson("L1.1", 0.5)
    assert db.lesson_progress("L1.1")["best_score"] == pytest.approx(0.9)


def test_xp_is_awarded_once_per_reason_and_ref(db):
    assert db.award_xp(10, "item_first_try", "L1.1/build")
    assert not db.award_xp(10, "item_first_try", "L1.1/build")
    assert db.total_xp() == 10


def test_spaced_repetition_schedule_and_resolution(db):
    db.add_mistake("L1.1/build", "L1.1", "references", "Q", "=1", "=B3*B4", "No cell references")
    m = db.mistakes()[0]
    today = dt.date(2026, 1, 1)
    assert dt.date.fromisoformat(m["next_review"]) > dt.date.today() - dt.timedelta(days=1)
    r = db.review_mistake(m["id"], False, today)
    assert r["next_review"] == "2026-01-02" and not r["resolved"]
    expected = ["2026-01-04", "2026-01-08"]
    for exp in expected:
        r = db.review_mistake(m["id"], True, today)
        assert r["next_review"] == exp and not r["resolved"]
    r = db.review_mistake(m["id"], True, today)
    assert r["resolved"]
    assert db.mistakes() == [] and len(db.mistakes(include_resolved=True)) == 1


def test_wrong_review_resets_streak(db):
    db.add_mistake("x", "L1.1", "s", "Q", "a", "b", "e")
    mid = db.mistakes()[0]["id"]
    today = dt.date(2026, 1, 1)
    db.review_mistake(mid, True, today)
    db.review_mistake(mid, True, today)
    db.review_mistake(mid, False, today)
    r = db.review_mistake(mid, True, today)
    assert not r["resolved"]


def test_backup_and_restore_round_trip(db, tmp_path):
    db.start_lesson("L1.1", "guided")
    db.complete_lesson("L1.1", 1.0)
    b = db.backup(tmp_path / "b.zip")
    db.reset_all()
    assert db.lesson_progress("L1.1") is None
    db.restore(b)
    assert db.lesson_progress("L1.1")["status"] == "completed"


def test_restore_rejects_non_backup(db, tmp_path):
    import zipfile
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("hello.txt", "hi")
    with pytest.raises(ValueError):
        db.restore(bad)


def test_restore_never_overwrites_a_different_project(db, tmp_path):
    from finpilot.config import projects_dir
    f = projects_dir() / "Model.finpilot"
    f.write_text("original backup copy", encoding="utf-8")
    b = db.backup(tmp_path / "b.zip", extra_files=[f])
    f.write_text("newer work", encoding="utf-8")
    restored = db.restore(b)
    assert f.read_text(encoding="utf-8") == "newer work"
    assert restored == ["Model (restored).finpilot"]


def test_corrupted_database_is_moved_aside_and_recreated(tmp_path):
    p = tmp_path / "finpilot.db"
    p.write_bytes(b"this is not a sqlite database at all" * 100)
    d = Database(p)
    assert d.recovered_from is not None and d.recovered_from.exists()
    assert d.integrity_ok()
    d.set_setting("theme", "dark")
    assert d.get_setting("theme") == "dark"
    d.close()


# ---------------------------------------------------------------- project files
def test_project_save_load_round_trip(tmp_path):
    p = pj.new_hotel_project("Test model")
    p.sheet.set("B15", "=$B$4*B9")
    p.state["recommendation"] = "Protect rate in winter."
    path = pj.save(p, tmp_path / "m.finpilot")
    q = pj.load(path)
    assert q.name == "Test model" and q.sheet.raw("B15") == "=$B$4*B9"
    assert q.sheet.value("B15") == 5580
    assert q.state["recommendation"] == "Protect rate in winter."
    assert H.compute(q.forecast).total.room_revenue == pytest.approx(H.compute(p.forecast).total.room_revenue)
    assert not q.checksum_warning


def test_second_save_keeps_a_bak(tmp_path):
    p = pj.new_hotel_project()
    path = pj.save(p, tmp_path / "m.finpilot")
    pj.save(p, path)
    assert (tmp_path / "m.finpilot.bak").exists()


@pytest.mark.parametrize("content", ["", "{not json", json.dumps({"app": "Other"}), "[1,2,3]"])
def test_corrupted_project_files_give_clear_errors(tmp_path, content):
    f = tmp_path / "bad.finpilot"
    f.write_text(content, encoding="utf-8")
    with pytest.raises(pj.ProjectError) as e:
        pj.load(f)
    assert "bad.finpilot" in str(e.value)


def test_binary_and_missing_files(tmp_path):
    b = tmp_path / "bin.finpilot"
    b.write_bytes(bytes(range(256)) * 10)
    with pytest.raises(pj.ProjectError):
        pj.load(b)
    with pytest.raises(pj.ProjectError):
        pj.load(tmp_path / "nope.finpilot")


def test_edited_file_opens_with_checksum_warning(tmp_path):
    path = pj.save(pj.new_hotel_project(), tmp_path / "m.finpilot")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["payload"]["name"] = "Edited by hand"
    path.write_text(json.dumps(data), encoding="utf-8")
    q = pj.load(path)
    assert q.checksum_warning and q.name == "Edited by hand"


def test_eleven_month_file_rejected(tmp_path):
    path = pj.save(pj.new_hotel_project(), tmp_path / "m.finpilot")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["payload"]["forecast"]["months"] = data["payload"]["forecast"]["months"][:11]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(pj.ProjectError):
        pj.load(path)
