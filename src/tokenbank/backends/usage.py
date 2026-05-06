"""Backend usage and cost helpers."""

from __future__ import annotations

from tokenbank.core.canonical import canonical_json_hash
from tokenbank.models.backend import UsageRecord
from tokenbank.models.common import CostConfidence, CostSource


def make_usage_record(
    *,
    work_unit_id: str,
    attempt_id: str,
    backend_id: str,
    input_units: int = 0,
    output_units: int = 0,
    estimated_cost_micros: int = 0,
    actual_cost_micros: int = 0,
    cost_source: CostSource = "not_applicable",
    cost_confidence: CostConfidence = "not_applicable",
) -> UsageRecord:
    usage_record_id = "usage_" + canonical_json_hash(
        {
            "work_unit_id": work_unit_id,
            "attempt_id": attempt_id,
            "backend_id": backend_id,
            "input_units": input_units,
            "output_units": output_units,
            "estimated_cost_micros": estimated_cost_micros,
            "actual_cost_micros": actual_cost_micros,
            "cost_source": cost_source,
            "cost_confidence": cost_confidence,
        }
    )[:24]
    return UsageRecord(
        usage_record_id=usage_record_id,
        work_unit_id=work_unit_id,
        attempt_id=attempt_id,
        backend_id=backend_id,
        input_units=input_units,
        output_units=output_units,
        estimated_cost_micros=estimated_cost_micros,
        actual_cost_micros=actual_cost_micros,
        cost_source=cost_source,
        cost_confidence=cost_confidence,
    )

