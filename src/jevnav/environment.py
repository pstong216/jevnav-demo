from __future__ import annotations

from typing import Protocol

from .models import RobotState


class RobotEnvironment(Protocol):
    def observe(self) -> RobotState: ...
    def step(self, action: str) -> RobotState: ...


class MockKitchenEnvironment:
    """Tiny semantic kitchen state machine used by the demo and tests."""

    def __init__(self) -> None:
        self._stage = 0
        self._history: list[str] = []

    def observe(self) -> RobotState:
        actions_by_stage = {
            0: ("navigate_to:mug_1", "inspect:counter", "replan", "stop"),
            1: ("pick_up:mug_1", "navigate_to:sink_1", "replan", "stop"),
            2: ("navigate_to:sink_1", "replan", "stop"),
            3: ("place:mug_1:sink_1", "replan", "stop"),
            4: ("stop",),
        }
        return RobotState(
            goal="Put the mug into the sink",
            room="kitchen",
            holding="mug_1" if 2 <= self._stage <= 3 else None,
            visible_objects=(
                {"id": "mug_1", "type": "mug", "location":
                 "sink" if self._stage == 4 else "held" if self._stage >= 2 else "table"},
                {"id": "sink_1", "type": "sink", "location": "north_wall"},
            ),
            legal_actions=actions_by_stage[self._stage],
            history=tuple(self._history),
            task_complete=self._stage == 4,
        )

    def step(self, action: str) -> RobotState:
        state = self.observe()
        if action not in state.legal_actions:
            raise ValueError(f"Illegal action {action!r}")
        self._history.append(action)
        expected = (
            "navigate_to:mug_1",
            "pick_up:mug_1",
            "navigate_to:sink_1",
            "place:mug_1:sink_1",
        )
        if self._stage < len(expected) and action == expected[self._stage]:
            self._stage += 1
        return self.observe()
