from __future__ import annotations

from typing import Any

from .models import RobotState


class AI2ThorAdapter:
    """Minimal AI2-THOR state adapter; semantic skill execution is future work."""

    def __init__(self, scene: str = "FloorPlan1", goal: str = "Explore safely") -> None:
        try:
            from ai2thor.controller import Controller
        except ImportError as exc:
            raise RuntimeError("Install AI2-THOR support with: pip install -e '.[thor]'") from exc
        self.controller = Controller(scene=scene)
        self.goal = goal
        self.event = self.controller.last_event
        self.history: list[str] = []

    def observe(self) -> RobotState:
        metadata: dict[str, Any] = self.event.metadata
        visible = tuple(
            {
                "id": obj["objectId"],
                "type": obj["objectType"],
                "location": obj.get("position", {}),
            }
            for obj in metadata.get("objects", [])
            if obj.get("visible")
        )
        return RobotState(
            goal=self.goal,
            room=str(metadata.get("sceneName", "unknown")),
            holding=None,
            visible_objects=visible,
            legal_actions=("move_ahead", "rotate_left", "rotate_right", "stop"),
            history=tuple(self.history),
        )

    def step(self, action: str) -> RobotState:
        action_map = {
            "move_ahead": "MoveAhead",
            "rotate_left": "RotateLeft",
            "rotate_right": "RotateRight",
        }
        if action == "stop":
            return self.observe()
        if action not in action_map:
            raise NotImplementedError(
                "Semantic AI2-THOR skills are not wired yet; use a discrete motion action."
            )
        self.event = self.controller.step(action=action_map[action])
        self.history.append(action)
        return self.observe()

    def close(self) -> None:
        self.controller.stop()

