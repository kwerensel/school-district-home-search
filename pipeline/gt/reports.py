from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gt.db.migrate import repo_root


@dataclass(frozen=True)
class ValidationReport:
    report_type: str
    target: str
    checks: dict[str, Any]
    promotable: bool = False
    status: str = "scaffolded"
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type,
            "target": self.target,
            "status": self.status,
            "generated_at": self.generated_at,
            "promotable": self.promotable,
            "checks": self.checks,
        }


def reports_dir() -> Path:
    path = repo_root() / "data" / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_report(report: ValidationReport, filename: str) -> Path:
    path = reports_dir() / filename
    payload = json.dumps(report.as_dict(), indent=2, sort_keys=True)
    path.write_text(payload)
    (reports_dir() / "latest.json").write_text(payload)
    return path


def read_report(name: str = "latest") -> dict[str, Any]:
    path = reports_dir() / f"{name}.json"
    if name.endswith(".json"):
        path = reports_dir() / name
    return json.loads(path.read_text())
