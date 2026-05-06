"""Baseline handling for derived cost reports."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Literal

BaselineMode = Literal["measured", "estimated", "none"]
BASELINE_MODES = {"measured", "estimated", "none"}


@dataclass(frozen=True)
class Baseline:
    mode: BaselineMode
    baseline_cost_micros: int | None
    caveats: tuple[str, ...]

    def saving_ratio_bps(self, observed_cost_micros: int) -> int | None:
        if self.mode == "none" or not self.baseline_cost_micros:
            return None
        return int(
            (self.baseline_cost_micros - observed_cost_micros)
            * 10_000
            / self.baseline_cost_micros
        )


def normalize_baseline_mode(value: str) -> BaselineMode:
    if value not in BASELINE_MODES:
        raise ValueError("baseline_mode must be measured, estimated, or none")
    return value  # type: ignore[return-value]


def resolve_baseline(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    baseline_mode: str = "none",
    estimated_cost_micros: int = 0,
) -> Baseline:
    mode = normalize_baseline_mode(baseline_mode)
    if mode == "none":
        return Baseline(
            mode="none",
            baseline_cost_micros=None,
            caveats=("baseline_mode=none; no savings claim is generated.",),
        )
    if mode == "estimated":
        return Baseline(
            mode="estimated",
            baseline_cost_micros=max(0, estimated_cost_micros),
            caveats=("baseline_mode=estimated; savings are estimated only.",),
        )

    measured = _measured_baseline_cost(conn, run_id)
    if measured is None:
        return Baseline(
            mode="measured",
            baseline_cost_micros=None,
            caveats=("baseline_mode=measured but no measured baseline was found.",),
        )
    return Baseline(mode="measured", baseline_cost_micros=measured, caveats=())


def _measured_baseline_cost(conn: sqlite3.Connection, run_id: str) -> int | None:
    row = conn.execute(
        """
        SELECT body_json
        FROM baseline_run_records
        WHERE run_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        body = json.loads(row["body_json"])
    except json.JSONDecodeError:
        return None
    value = body.get("baseline_cost_micros")
    return value if isinstance(value, int) and value >= 0 else None
