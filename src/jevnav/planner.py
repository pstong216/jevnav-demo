"""Background subgoal planning with one in-flight request and stale-result rejection."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import json
import os
import time

from .api import APIError, post_json


@dataclass(frozen=True)
class Plan:
    objective: str
    waypoint: tuple[int, int] | None
    notes: str
    model: str


def validate_plan(value, state, model):
    if not isinstance(value, dict):
        raise ValueError("Plan must be an object")
    objective, waypoint, notes = value.get("objective"), value.get("waypoint"), value.get("notes", "")
    if not isinstance(objective, str) or not objective.strip() or len(objective) > 1000:
        raise ValueError("Invalid objective")
    if not isinstance(notes, str) or len(notes) > 2000:
        raise ValueError("Invalid notes")
    if waypoint is not None:
        if (not isinstance(waypoint, (list, tuple)) or len(waypoint) != 2
                or any(type(n) is not int for n in waypoint)):
            raise ValueError("Invalid waypoint")
        waypoint = tuple(waypoint)
        c = state.context
        blocked = {tuple(p) for p in c["walls"] + c["obstacles"]}
        if (not 0 <= waypoint[0] < c["size"][0] or not 0 <= waypoint[1] < c["size"][1]
                or waypoint in blocked):
            raise ValueError("Waypoint is blocked or outside map")
    return Plan(objective.strip(), waypoint, notes, model)


class RulePlanner:
    """Offline wiring check; not a language model."""
    def plan(self, state):
        return Plan(state.context["subgoal"], tuple(state.context["target"]),
                    "Rule-based subgoal; use collision-free navigation", "rule planner (not LLM)")


class OpenRouterPlanner:
    def __init__(self, model, api_key=None, transport=post_json):
        self.key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.key or self.key == "replace_me":
            raise APIError("Set OPENROUTER_API_KEY before enabling the LLM planner")
        if not model:
            raise APIError("Specify --planner-model with an OpenRouter model supporting JSON mode")
        self.model, self.transport = model, transport

    def plan(self, state):
        payload = {"model": self.model, "response_format": {"type": "json_object"},
                   "provider": {"require_parameters": True}, "max_tokens": 500,
                   "messages": [
                       {"role": "system", "content":
                        "Plan the next subgoal for a robot in a fully observed 2D kitchen. "
                        "Return JSON only: {objective: string, waypoint: [x,y] or null, notes: string}. "
                        "Choose a reachable intermediate waypoint or task target. Never place "
                        "waypoints on walls or obstacles. x increases east, y increases south. "
                        "Account for holding status and newly blocked doorways. You provide "
                        "guidance; another model selects executable actions. Do not claim completion "
                        "unless environment task_complete is true."},
                       {"role": "user", "content": state.as_prompt()}]}
        response = self.transport("https://openrouter.ai/api/v1/chat/completions", self.key, payload)
        try:
            value = json.loads(response["choices"][0]["message"]["content"])
            return validate_plan(value, state, self.model)
        except (KeyError, IndexError, TypeError, ValueError):
            raise APIError("Planner returned an invalid plan") from None


class BackgroundPlanner:
    def __init__(self, backend, executor=None):
        self.backend = backend
        self.executor = executor or ThreadPoolExecutor(max_workers=1)
        self.pending = None
        self.generation = 0
        self.reset()

    def reset(self):
        self.generation += 1
        self.current = None
        self.current_key = None
        self.last_step = -8
        self.force = False
        self.error = None
        self.events = []

    @staticmethod
    def key(state):
        return state.context["revision"], state.context["subgoal"]

    def tick(self, state, step):
        key = self.key(state)
        if self.current_key != key:
            self.current = None
        if self.pending and self.pending[0].done():
            future, request_key, generation, started = self.pending
            self.pending = None
            if (request_key, generation) != (key, self.generation):
                self.events.append({"event": "discarded_stale_plan"})
            else:
                try:
                    plan = future.result()
                    # Revalidate on acceptance against current geometry.
                    self.current = validate_plan(asdict(plan), state, plan.model)
                    self.current_key = key
                    self.events.append({"event": "plan_ready", "plan": asdict(self.current),
                                        "latency_ms": round((time.monotonic()-started)*1000, 1)})
                except Exception:
                    self.error = "Planner failed or returned an invalid plan; reset to retry"
                    self.events.append({"event": "planner_error", "error": self.error})
        reached = (self.current and self.current.waypoint == tuple(state.context["position"])
                   and not any(a.startswith(("pick_up:", "place:")) for a in state.legal_actions))
        if (not self.pending and not self.error and not state.task_complete
                and (not self.current or self.force or reached or step-self.last_step >= 8)):
            self.pending = (self.executor.submit(self.backend.plan, state), key,
                            self.generation, time.monotonic())
            self.last_step = step
            self.force = False

    def snapshot(self):
        return {"enabled": True, "pending": self.pending is not None,
                "plan": asdict(self.current) if self.current else None,
                "error": self.error, "events": list(self.events)}

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
