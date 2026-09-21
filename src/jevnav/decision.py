from __future__ import annotations

from typing import Protocol
import math
import os

from .api import APIError, post_json
from .models import Decision, RobotState


class DecisionEngine(Protocol):
    def decide(self, state: RobotState) -> Decision: ...


class MockDecisionEngine:
    """A deterministic decision engine for a credential-free demo."""

    def decide(self, state: RobotState) -> Decision:
        if state.task_complete and "stop" in state.legal_actions:
            action = "stop"
        elif state.holding == "mug_1" and "navigate_to:sink_1" in state.legal_actions:
            action = "navigate_to:sink_1"
        elif state.holding == "mug_1" and "place:mug_1:sink_1" in state.legal_actions:
            action = "place:mug_1:sink_1"
        elif "navigate_to:mug_1" in state.legal_actions:
            action = "navigate_to:mug_1"
        elif "pick_up:mug_1" in state.legal_actions:
            action = "pick_up:mug_1"
        else:
            action = "stop"

        count = len(state.legal_actions)
        probabilities = {
            candidate: (0.96 if candidate == action else 0.04 / (count - 1))
            for candidate in state.legal_actions
        } if count > 1 else {action: 1.0}
        return Decision(
            action=action,
            action_confidence=probabilities[action],
            probabilities=probabilities,
            unsafe_probability=0.01,
            needs_planner_probability=0.02,
            complete_probability=0.99 if state.task_complete else 0.01,
            model="mock-reflex",
        )


class TypeSafeJevEngine:
    """Official TypeSafe HTTP contract; no optional SDK dependency required."""

    def __init__(self, api_key=None, model=None, transport=post_json) -> None:
        self.key = api_key or os.environ.get("TYPESAFE_API_KEY")
        if not self.key or self.key == "replace_me":
            raise APIError("Set TYPESAFE_API_KEY in your terminal before selecting Jev")
        self.model = model or os.environ.get("JEV_MODEL", "jev-latest")
        self.transport = transport

    def decide(self, state: RobotState) -> Decision:
        criteria = {a: _describe_action(a) for a in state.legal_actions}
        questions = {
            "next_action": {"type": "choice", "criteria": criteria,
                "instructions": "Choose one legal action advancing the goal and current planner "
                "objective, if provided. Move one cell at a time, avoid obstacles and repeated "
                "loops. Pick/place when at the target. Stop only if complete or no safe progress "
                "is possible. Replan if the plan is unsuitable; do not invent actions."},
            "needs_planner": {"type": "noul", "instructions":
                "Is the current planner objective missing necessary guidance or unsuitable "
                "for the current map, such that a fresh plan is needed?"},
            "complete": {"type": "noul", "instructions":
                "Has the mug been placed at its required destination?"},
        }
        risk_ids = {a: f"risk_{i}" for i, a in enumerate(state.legal_actions)}
        for action, question_id in risk_ids.items():
            questions[question_id] = {"type": "noul", "instructions":
                f"Would executing this specific action NOW cause collision or property risk: "
                f"{action} ({criteria[action]})? Assess against observed geometry and state."}
        response = self.transport("https://api.typesafe.ai/v1/systemone", self.key,
                                  {"model": self.model, "state": state.as_prompt(),
                                   "questions": questions})
        try:
            answers = response["answers"]
            answer = answers["next_action"]
            action = answer["choice"]
            if action not in criteria or answer["type"] != "choice":
                raise ValueError("invalid action")
            probabilities = {a: _probability(p) for a, p in answer["probabilities"].items()}
            if set(probabilities) != set(criteria) or not math.isclose(
                    sum(probabilities.values()), 1, abs_tol=0.01):
                raise ValueError("invalid distribution")
            def noul(key):
                if answers[key]["type"] != "noul":
                    raise ValueError("invalid noul")
                return _probability(answers[key]["noul"])
            return Decision(
                action=action, action_confidence=_probability(answer["confidence"]),
                probabilities=probabilities, unsafe_probability=noul(risk_ids[action]),
                needs_planner_probability=noul("needs_planner"),
                complete_probability=noul("complete"), model=str(response["model"]),
                usage={k: v for k, v in response.get("usage", {}).items()
                       if type(v) is int and v >= 0})
        except (KeyError, TypeError, ValueError, AttributeError):
            raise APIError("Jev returned an invalid decision; execution stopped") from None


def _probability(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Invalid probability")
    return float(value)


def _describe_action(action: str) -> str:
    verb, *args = action.split(":")
    descriptions = {
        "navigate_to": "Use the navigation controller to approach the target",
        "pick_up": "Pick up the target object when reachable",
        "place": "Place the held object into or onto the destination",
        "inspect": "Inspect a location to obtain more state information",
        "replan": "Request a new high-level plan",
        "stop": "Stop because the task is complete or no safe action exists",
        "move": "Move one grid cell in the specified direction (north y-1, east x+1, south y+1, west x-1)",
        "wait": "Remain in place for one step",
    }
    suffix = f" ({', '.join(args)})" if args else ""
    return descriptions.get(verb, f"Execute {verb}") + suffix
