"""Verifier recipe YAML loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

RECIPE_DIR = Path(__file__).parent / "recipes"


@dataclass(frozen=True)
class VerifierRecipe:
    verifier_recipe_id: str
    task_type: str
    output_schema: dict[str, Any]
    recommendations: dict[str, str]
    sampled_audit_rate_bps: int = 0

    def recommendation(self, key: str, default: str = "reject") -> str:
        return str(self.recommendations.get(key, default))


def load_verifier_recipe(
    verifier_recipe_id: str,
    *,
    recipe_dir: Path = RECIPE_DIR,
) -> VerifierRecipe:
    path = recipe_dir / f"{verifier_recipe_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"unknown verifier recipe: {verifier_recipe_id}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    recipe = payload.get("verifier_recipe", {})
    return VerifierRecipe(
        verifier_recipe_id=str(recipe["verifier_recipe_id"]),
        task_type=str(recipe["task_type"]),
        output_schema=dict(recipe.get("output_schema", {})),
        recommendations=dict(recipe.get("recommendations", {})),
        sampled_audit_rate_bps=int(recipe.get("sampled_audit_rate_bps", 0)),
    )


def load_all_verifier_recipes(
    recipe_dir: Path = RECIPE_DIR,
) -> dict[str, VerifierRecipe]:
    recipes: dict[str, VerifierRecipe] = {}
    for path in sorted(recipe_dir.glob("*.yaml")):
        recipe_id = path.stem
        recipes[recipe_id] = load_verifier_recipe(recipe_id, recipe_dir=recipe_dir)
    return recipes
