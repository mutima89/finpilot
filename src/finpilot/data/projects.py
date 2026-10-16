"""Project files (.finpilot): JSON documents with a version and checksum.

Saving is atomic: the file is written to a temporary name and then swapped in,
and the previous version is kept as ``<name>.finpilot.bak``. Loading validates
the format, version and checksum and raises ``ProjectError`` with a plain
explanation when a file is damaged or incomplete.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .. import __version__
from ..core.hotel import HotelAssumptions, default_budget, default_forecast
from ..core.sheet import Sheet

FORMAT = "finpilot-project"
VERSION = 1
EXTENSION = ".finpilot"


class ProjectError(Exception):
    pass


@dataclass
class Project:
    name: str = "Untitled model"
    kind: str = "hotel_model"          # hotel_model | lab
    sheet: Sheet = field(default_factory=lambda: Sheet("Model"))
    forecast: HotelAssumptions = field(default_factory=default_forecast)
    budget: HotelAssumptions = field(default_factory=default_budget)
    state: dict = field(default_factory=dict)   # guided-project progress, notes, recommendation text
    path: Optional[Path] = None
    created: str = field(default_factory=lambda: dt.datetime.now().isoformat(timespec="seconds"))
    checksum_warning: bool = False

    def payload(self) -> dict:
        return {
            "name": self.name, "kind": self.kind, "created": self.created,
            "modified": dt.datetime.now().isoformat(timespec="seconds"),
            "app_version": __version__,
            "sheet": self.sheet.to_dict(),
            "forecast": self.forecast.to_dict(), "budget": self.budget.to_dict(),
            "state": self.state,
        }


def _checksum(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def save(project: Project, path: Optional[Path] = None) -> Path:
    path = Path(path or project.path or "")
    if not str(path):
        raise ProjectError("No file name given.")
    if path.suffix.lower() != EXTENSION:
        path = path.with_suffix(EXTENSION)
    payload = project.payload()
    doc = {"format": FORMAT, "version": VERSION, "checksum": _checksum(payload), "payload": payload}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    if path.exists():
        bak = path.with_name(path.name + ".bak")
        try:
            if bak.exists():
                bak.unlink()
            os.replace(path, bak)
        except OSError:
            pass
    os.replace(tmp, path)
    project.path = path
    return path


def load(path: Path) -> Project:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ProjectError(f"The file {path.name} no longer exists.")
    except UnicodeDecodeError:
        raise ProjectError(f"{path.name} is not a FinPilot project (it is not a text file).")
    if not text.strip():
        raise ProjectError(f"{path.name} is empty. It may have been interrupted while saving; "
                           f"try the backup copy {path.name}.bak if it exists.")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise ProjectError(f"{path.name} is damaged or incomplete (invalid JSON at line {e.lineno}). "
                           f"Try the backup copy {path.name}.bak if it exists.")
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise ProjectError(f"{path.name} is not a FinPilot project file.")
    if int(doc.get("version", 0)) > VERSION:
        raise ProjectError(f"{path.name} was created by a newer version of FinPilot.")
    payload = doc.get("payload")
    if not isinstance(payload, dict):
        raise ProjectError(f"{path.name} is missing its model data.")
    mismatch = doc.get("checksum") != _checksum(payload)
    try:
        p = Project(
            name=str(payload.get("name", path.stem)), kind=str(payload.get("kind", "hotel_model")),
            sheet=Sheet.from_dict(payload["sheet"]),
            forecast=HotelAssumptions.from_dict(payload["forecast"]) if "forecast" in payload else default_forecast(),
            budget=HotelAssumptions.from_dict(payload["budget"]) if "budget" in payload else default_budget(),
            state=dict(payload.get("state", {})), path=path, created=str(payload.get("created", "")))
    except (KeyError, TypeError, ValueError, IndexError) as e:
        raise ProjectError(f"{path.name} is incomplete or contains invalid data ({type(e).__name__}: {e}).")
    if p.forecast.months and len(p.forecast.months) != 12:
        raise ProjectError(f"{path.name} has {len(p.forecast.months)} months of forecast data; 12 are required.")
    p.checksum_warning = mismatch
    return p


def new_hotel_project(name: str = "Harbour Crest revenue model", guided: bool = True) -> Project:
    from ..core.hotel_sheet import build_sheet
    f, b = default_forecast(), default_budget()
    return Project(name=name, kind="hotel_model", sheet=build_sheet(f, b, include_calcs=not guided),
                   forecast=f, budget=b, state={"guided": guided})


def to_json_safe(v: Any) -> Any:
    return json.loads(json.dumps(v, default=str))
