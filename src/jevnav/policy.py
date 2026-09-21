from __future__ import annotations

from dataclasses import dataclass

from .decision import DecisionEngine
from .models import Decision, RobotState


@dataclass
class ReflexPolicy:
    engine: DecisionEngine
    min_action_confidence: float = 0.55
    max_unsafe_probability: float = 0.70
    planner_threshold: float = 0.65

    def act(self, state: RobotState) -> Decision:
        decision = self.engine.decide(state)
        if decision.action not in state.legal_actions:
            return self._gate(decision, "replan", state)
        if decision.unsafe_probability >= self.max_unsafe_probability:
            return self._gate(decision, "stop", state)
        if (
            decision.action_confidence < self.min_action_confidence
            or decision.needs_planner_probability >= self.planner_threshold
        ):
            return self._gate(decision, "replan", state)
        return decision

    @staticmethod
    def _gate(decision: Decision, preferred: str, state: RobotState) -> Decision:
        action = preferred if preferred in state.legal_actions else "stop"
        if action not in state.legal_actions:
            raise RuntimeError("Decision rejected; no legal stop or replan action exists")
        return Decision(
            action=action,
            action_confidence=decision.action_confidence,
            probabilities=decision.probabilities,
            unsafe_probability=decision.unsafe_probability,
            needs_planner_probability=decision.needs_planner_probability,
            complete_probability=decision.complete_probability,
            model=f"{decision.model}+gate",
        )
