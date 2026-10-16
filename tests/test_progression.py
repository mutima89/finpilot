"""Learning path rules: scoring, prerequisites, unlocking, recommendations, XP, badges and competency."""

from finpilot.curriculum import progression as prog


def complete(db, *ids, score=1.0):
    for i in ids:
        db.start_lesson(i, "guided")
        db.complete_lesson(i, score)


def level_lessons(cur, n):
    return [l.id for l in cur.level(n).lessons if l.kind == "lesson"]


def test_item_scores_reward_first_attempts_and_zero_reveals():
    assert prog.item_score(1, True) == 1.0
    assert prog.item_score(2, True) == 0.6
    assert prog.item_score(5, True) == 0.3
    assert prog.item_score(1, True, revealed=True) == 0.0
    assert prog.item_score(1, False) == 0.0


def test_new_learner_starts_at_first_lesson(cur, db):
    rec = prog.next_recommendation(cur, db)
    assert rec.kind == "lesson" and rec.ref == "L1.1"
    assert prog.lesson_status(cur, db, cur.lesson("L1.1")) == "available"
    assert prog.lesson_status(cur, db, cur.lesson("L1.2")) == "locked"
    assert not prog.level_unlocked(cur, db, 2)
    assert not prog.final_assessment_unlocked(cur, db)


def test_prerequisites_unlock_in_order(cur, db):
    complete(db, "L1.1")
    assert prog.lesson_status(cur, db, cur.lesson("L1.2")) == "available"
    assert prog.missing_prereqs(cur, db, cur.lesson("L2.1"))


def test_completing_level_unlocks_next(cur, db):
    complete(db, *level_lessons(cur, 1))
    assert prog.level_unlocked(cur, db, 2)
    assert prog.current_level(cur, db) in (1, 2)  # P1 project may still be open on level 1


def test_planned_levels_never_unlock(cur, db):
    complete(db, *[l.id for l in cur.lessons])
    assert not prog.level_unlocked(cur, db, 7)


def test_unlock_all_setting(cur, db):
    db.set_setting("unlock_all", True)
    assert prog.lesson_status(cur, db, cur.lesson("L3.6")) == "available"
    assert prog.final_assessment_unlocked(cur, db)


def test_mastery_threshold(cur, db):
    complete(db, "L1.1", score=0.79)
    assert prog.lesson_status(cur, db, cur.lesson("L1.1")) == "completed"
    complete(db, "L1.1", score=0.8)
    assert prog.lesson_status(cur, db, cur.lesson("L1.1")) == "mastered"


def test_due_reviews_are_recommended_first(cur, db):
    import datetime as dt
    complete(db, "L1.1")
    db.add_mistake("L1.1/build", "L1.1", "references", "Q", "a", "b", "e")
    later = dt.date.today() + dt.timedelta(days=2)
    # one due item does not interrupt the path...
    assert prog.next_recommendation(cur, db, later).kind == "lesson"
    # ...but three or more due items come first
    db.add_mistake("L1.1/apply", "L1.1", "references", "Q", "a", "b", "e")
    db.add_mistake("L1.1/recall-0", "L1.1", "references", "Q", "a", "b", "e")
    assert prog.next_recommendation(cur, db, later).kind == "review"


def test_final_assessment_recommended_after_all_lessons(cur, db):
    complete(db, *[l.id for l in cur.lessons if l.kind != "lab_project"])
    rec = prog.next_recommendation(cur, db)
    assert rec.kind in ("assessment", "project", "lab")


def test_xp_award_is_idempotent_and_badges_are_meaningful(cur, db):
    assert prog.award(db, "lesson_complete", "L1.1") == prog.XP_RULES["lesson_complete"]
    assert prog.award(db, "lesson_complete", "L1.1") == 0
    complete(db, *level_lessons(cur, 1))
    assert "foundations" in prog.check_badges(cur, db)
    assert "foundations" not in prog.check_badges(cur, db)     # awarded once


def test_competency_needs_evidence_not_screens(cur, db):
    complete(db, *[l.id for l in cur.lessons])                 # finished screens, no evidence
    statuses = {c.skill_id: c.status for c in prog.competencies(cur, db)}
    assert set(statuses.values()) == {"not_assessed"}


def test_hotel_model_skill_requires_validated_model(cur, db):
    db.add_evidence(["hotel_model"], "lesson:L3.5/build", 1.0, 1.0)
    st = {c.skill_id: c for c in prog.competencies(cur, db)}["hotel_model"]
    assert st.status != "demonstrated"
    db.add_evidence(["hotel_model"], "model:P3", 1.0, 3.0)
    st = {c.skill_id: c for c in prog.competencies(cur, db)}["hotel_model"]
    assert st.status == "demonstrated"


def test_weak_evidence_needs_practice(cur, db):
    db.add_evidence(["references"], "lesson:L2.2/build", 0.0, 1.0)
    db.add_evidence(["references"], "lesson:L2.2/apply", 0.3, 1.0)
    st = {c.skill_id: c for c in prog.competencies(cur, db)}["references"]
    assert st.status == "needs_practice"


def test_competency_report_contents(cur, db):
    rep = prog.competency_report(cur, db)
    for key in ("demonstrated", "developing", "needs_practice", "not_assessed", "assessments", "next_step",
                "model_validated", "criteria", "outstanding", "xp"):
        assert key in rep
