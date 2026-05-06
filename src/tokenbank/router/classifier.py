"""Router task classification helpers."""

from __future__ import annotations

from typing import Any

from tokenbank.routebook.loader import LoadedRoutebook
from tokenbank.routebook.task_level_classifier import classify_task_level


class TaskClassifier:
    def __init__(self, routebook: LoadedRoutebook):
        self.routebook = routebook

    def classify(self, work_unit: dict[str, Any]) -> str:
        return classify_task_level(work_unit, self.routebook)

