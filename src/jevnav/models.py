from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RobotState:
    goal: str
    room: str
    holding: str | None
    visible_objects: tuple[dict[str, Any], ...]
    legal_actions: tuple[str, ...]
    history: tuple[str, ...] = ()
    task_complete: bool = False

    def as_prompt(self) -> str:
        objects = ", ".join(
            f"{obj['id']} ({obj['type']}, location={obj.get('location', 'unknown')})"
            for obj in self.visible_objects
        )
        return (
            f"Goal: {self.goal}\n"
            f"Robot room: {self.room}\n"
            f"Holding: {self.holding or 'nothing'}\n"
            f"Visible objects: {objects or 'none'}\n"
            f"Legal actions: {', '.join(self.legal_actions)}\n"
            f"Action history: {', '.join(self.history) or 'none'}\n"
            f"Environment task-complete signal: {self.task_complete}"
        )


@dataclass(frozen=True)
class Decision:
    action: str
    action_confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)
    unsafe_probability: float = 0.0
    needs_planner_probability: float = 0.0
    complete_probability: float = 0.0
    model: str = "unknown"

