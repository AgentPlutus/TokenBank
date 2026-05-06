"""Deterministic WP-RB2 task analysis."""

from __future__ import annotations

from math import ceil
from pathlib import Path
from typing import Any

from tokenbank.config_runtime.loader import LoadedConfig, load_config_dir
from tokenbank.core.canonical import canonical_json_dumps
from tokenbank.models.route_plan import RouteCandidate, RoutePlan
from tokenbank.models.task_analysis import (
    ComplexityEstimate,
    CostEstimate,
    InputShape,
    TaskAnalysisReport,
)
from tokenbank.models.work_unit import WorkUnit
from tokenbank.routebook.v1_loader import LoadedRoutebookV1, load_routebook_v1_dir
from tokenbank.router.privacy_preflight import scan_privacy
from tokenbank.router.token_estimator import estimate_tokens

_TASK_LEVEL_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
_PRIVACY_ORDER = {"private": 0, "internal": 1, "sensitive": 2}
_DIFFICULTY_ORDER = {
    "trivial": 0,
    "easy": 1,
    "medium": 2,
    "high": 3,
    "expert": 4,
}


class TaskAnalyzer:
    """Analyze explicit input before scored routing."""

    def __init__(
        self,
        *,
        routebook_v1: LoadedRoutebookV1,
        loaded_config: LoadedConfig,
    ):
        self.routebook_v1 = routebook_v1
        self.loaded_config = loaded_config

    @classmethod
    def from_dirs(
        cls,
        *,
        config_dir: str | Path = "config",
        routebook_v1_dir: str | Path = "packs/base-routing/routebook",
    ) -> TaskAnalyzer:
        return cls(
            routebook_v1=load_routebook_v1_dir(routebook_v1_dir),
            loaded_config=load_config_dir(config_dir),
        )

    def analyze(
        self,
        *,
        work_unit: WorkUnit,
        route_plan: RoutePlan | None = None,
    ) -> TaskAnalysisReport:
        input_shape = input_shape_for_work_unit(work_unit)
        token_estimate = estimate_tokens(
            task_type=work_unit.task_type,
            inline_input=work_unit.inline_input,
        )
        privacy_scan = scan_privacy(work_unit.inline_input)
        task_defaults = self._task_type_defaults(work_unit.task_type)
        complexity = _complexity_estimate(
            task_defaults=task_defaults,
            input_shape=input_shape,
            token_total=token_estimate.estimated_total_tokens,
            route_plan=route_plan,
        )
        effective_privacy = _raised_privacy_level(
            current=work_unit.privacy_level,
            raw_secret_detected=privacy_scan.raw_secret_detected,
            private_data_detected=privacy_scan.private_data_detected,
        )
        effective_level = _raised_task_level(
            current=work_unit.task_level,
            difficulty=complexity.difficulty,
            raw_secret_detected=privacy_scan.raw_secret_detected,
            private_data_detected=privacy_scan.private_data_detected,
        )
        reason_codes = [
            "deterministic_wp_rb2_preflight",
            f"task_type:{work_unit.task_type}",
            f"tokenizer:{token_estimate.tokenizer_profile_id}",
        ]
        if input_shape.workspace_scan_requested:
            reason_codes.append("workspace_scan_requested_denied")
        if privacy_scan.raw_secret_detected:
            reason_codes.append("preflight_deny_raw_secret")
        if privacy_scan.private_data_detected:
            reason_codes.append("privacy_level_raised")
        if _TASK_LEVEL_ORDER[effective_level] > _TASK_LEVEL_ORDER[work_unit.task_level]:
            reason_codes.append("task_level_raised")

        return TaskAnalysisReport(
            task_analysis_id=f"ta_{work_unit.work_unit_id}_{work_unit.task_type}",
            work_unit_id=work_unit.work_unit_id,
            routebook_id=self.routebook_v1.routebook_id,
            routebook_version=self.routebook_v1.version,
            task_type=work_unit.task_type,
            input_shape=input_shape,
            token_estimate=token_estimate,
            cost_estimate=self._cost_estimate(
                token_estimate=token_estimate.model_dump(mode="json"),
                route_plan=route_plan,
            ),
            privacy_scan=privacy_scan,
            complexity=complexity,
            effective_task_level=effective_level,  # type: ignore[arg-type]
            effective_privacy_level=effective_privacy,  # type: ignore[arg-type]
            preflight_decision="deny"
            if privacy_scan.raw_secret_detected or input_shape.workspace_scan_requested
            else "allow",
            confidence=_analysis_confidence(
                input_shape=input_shape,
                raw_secret_detected=privacy_scan.raw_secret_detected,
            ),
            reason_codes=reason_codes,
        )

    def _task_type_defaults(self, task_type: str) -> dict[str, Any]:
        defaults = self.routebook_v1.ontology.get("task_type_defaults", {})
        if isinstance(defaults, dict) and isinstance(defaults.get(task_type), dict):
            return dict(defaults[task_type])
        return {}

    def _cost_estimate(
        self,
        *,
        token_estimate: dict[str, Any],
        route_plan: RoutePlan | None,
    ) -> CostEstimate:
        selected = _selected_candidate(route_plan)
        base_cost = selected.estimated_cost_micros if selected is not None else 0
        price = _price_for_backend(
            self.loaded_config,
            selected.backend_id if selected is not None else None,
        )
        input_tokens = int(token_estimate["estimated_input_tokens"])
        output_tokens = int(token_estimate["estimated_output_tokens"])
        token_cost = (
            input_tokens * price["input_unit_micros"]
            + output_tokens * price["output_unit_micros"]
        )
        expected = max(base_cost, token_cost)
        return CostEstimate(
            cost_profile_id=price["cost_profile_id"],
            min_cost_micros=0 if expected == 0 else max(1, ceil(expected * 0.5)),
            expected_cost_micros=expected,
            max_cost_micros=expected if expected == 0 else max(expected, expected * 2),
            confidence=0.80 if selected is not None else 0.55,
            cost_source="pricing_table_estimate" if token_cost else "backend_estimate",
        )


def input_shape_for_work_unit(work_unit: WorkUnit) -> InputShape:
    inline_input = work_unit.inline_input
    serialized = canonical_json_dumps(inline_input)
    return InputShape(
        explicit_refs_count=len(work_unit.input_refs),
        explicit_urls_count=_count_urls(inline_input),
        file_refs_count=_count_file_refs(inline_input),
        inline_chars=len(serialized),
        inline_bytes=len(serialized.encode("utf-8")),
        json_depth=_json_depth(inline_input),
        list_items_count=_list_items_count(inline_input),
        workspace_scan_requested=_workspace_scan_requested(inline_input),
    )


def _complexity_estimate(
    *,
    task_defaults: dict[str, Any],
    input_shape: InputShape,
    token_total: int,
    route_plan: RoutePlan | None,
) -> ComplexityEstimate:
    base_difficulty = str(task_defaults.get("difficulty", "medium"))
    difficulty = _raise_difficulty(
        base_difficulty,
        token_total=token_total,
        json_depth=input_shape.json_depth,
    )
    task_family = str(task_defaults.get("task_family", "simple_transform"))
    requires_tools = bool(route_plan and route_plan.candidates) and any(
        candidate.backend_class not in {"api_model_gateway", "primary_model_gateway"}
        for candidate in route_plan.candidates
    )
    reason_codes = [
        f"default_difficulty:{base_difficulty}",
        f"task_family:{task_family}",
    ]
    if difficulty != base_difficulty:
        reason_codes.append(f"difficulty_raised:{difficulty}")
    if token_total >= 16_000:
        reason_codes.append("long_context_estimate")
    if requires_tools:
        reason_codes.append("route_requires_tool_backend")
    return ComplexityEstimate(
        difficulty=difficulty,  # type: ignore[arg-type]
        estimated_attempts=_estimated_attempts(difficulty),
        requires_strong_reasoning=(
            difficulty in {"high", "expert"} or task_family == "strong_reasoning"
        ),
        requires_long_context=token_total >= 16_000,
        requires_tools=requires_tools,
        reason_codes=reason_codes,
    )


def _price_for_backend(
    loaded_config: LoadedConfig,
    backend_id: str | None,
) -> dict[str, int | str]:
    if backend_id is None:
        return {
            "cost_profile_id": "pricing:none",
            "input_unit_micros": 0,
            "output_unit_micros": 0,
        }
    for document in loaded_config.documents["pricing"].get("documents", []):
        pricing = document.get("pricing", {})
        for price in pricing.get("backend_prices", []):
            if price.get("backend_id") == backend_id:
                return {
                    "cost_profile_id": f"pricing:{backend_id}",
                    "input_unit_micros": int(price.get("input_unit_micros", 0)),
                    "output_unit_micros": int(price.get("output_unit_micros", 0)),
                }
    return {
        "cost_profile_id": f"backend_cost_model:{backend_id}",
        "input_unit_micros": 0,
        "output_unit_micros": 0,
    }


def _selected_candidate(route_plan: RoutePlan | None) -> RouteCandidate | None:
    if route_plan is None:
        return None
    for candidate in route_plan.candidates:
        if candidate.route_candidate_id == route_plan.selected_candidate_id:
            return candidate
    return None


def _raised_privacy_level(
    *,
    current: str,
    raw_secret_detected: bool,
    private_data_detected: bool,
) -> str:
    target = "sensitive" if raw_secret_detected or private_data_detected else current
    return _max_by_order(current, target, order=_PRIVACY_ORDER)


def _raised_task_level(
    *,
    current: str,
    difficulty: str,
    raw_secret_detected: bool,
    private_data_detected: bool,
) -> str:
    target = current
    if difficulty in {"high", "expert"}:
        target = "L2"
    if private_data_detected:
        target = "L1"
    if raw_secret_detected:
        target = "L2"
    return _max_by_order(current, target, order=_TASK_LEVEL_ORDER)


def _max_by_order(
    current: str,
    target: str,
    *,
    order: dict[str, int],
) -> str:
    if order[target] > order[current]:
        return target
    return current


def _raise_difficulty(
    base_difficulty: str,
    *,
    token_total: int,
    json_depth: int,
) -> str:
    target = base_difficulty
    if token_total >= 32_000:
        target = "expert"
    elif token_total >= 16_000:
        target = "high"
    elif json_depth >= 6:
        target = "medium"
    if _DIFFICULTY_ORDER[target] > _DIFFICULTY_ORDER.get(base_difficulty, 2):
        return target
    return base_difficulty


def _estimated_attempts(difficulty: str) -> float:
    return {
        "trivial": 1.0,
        "easy": 1.0,
        "medium": 1.2,
        "high": 1.5,
        "expert": 2.0,
    }.get(difficulty, 1.2)


def _analysis_confidence(
    *,
    input_shape: InputShape,
    raw_secret_detected: bool,
) -> float:
    if raw_secret_detected:
        return 0.90
    if input_shape.inline_chars > 20_000:
        return 0.70
    return 0.82


def _count_urls(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_count_urls(nested) for nested in value.values())
    if isinstance(value, list):
        return sum(_count_urls(item) for item in value)
    if isinstance(value, str):
        return value.count("http://") + value.count("https://")
    return 0


def _count_file_refs(value: Any) -> int:
    if isinstance(value, dict):
        count = 0
        for key, nested in value.items():
            key_text = str(key).lower()
            if isinstance(nested, str) and (
                key_text.endswith("_path")
                or key_text.endswith("_file")
                or key_text in {"path", "file"}
            ):
                count += 1
            count += _count_file_refs(nested)
        return count
    if isinstance(value, list):
        return sum(_count_file_refs(item) for item in value)
    return 0


def _json_depth(value: Any) -> int:
    if isinstance(value, dict):
        if not value:
            return 1
        return 1 + max(_json_depth(nested) for nested in value.values())
    if isinstance(value, list):
        if not value:
            return 1
        return 1 + max(_json_depth(item) for item in value)
    return 1


def _list_items_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_list_items_count(nested) for nested in value.values())
    if isinstance(value, list):
        return len(value) + sum(_list_items_count(item) for item in value)
    return 0


def _workspace_scan_requested(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key).lower().replace("-", "_")
            if "workspace" in key_text and "scan" in key_text:
                return True
            if key_text in {"recursive", "recursive_scan"} and bool(nested):
                return True
            if _workspace_scan_requested(nested):
                return True
        return False
    if isinstance(value, list):
        return any(_workspace_scan_requested(item) for item in value)
    return False
