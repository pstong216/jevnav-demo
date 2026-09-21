"""Discrete navigation sandbox. Full map observation; no physics or vision model."""
from collections import deque

from .models import Decision, RobotState


MOVES = {"move:north": (0, -1), "move:east": (1, 0),
         "move:south": (0, 1), "move:west": (-1, 0)}


class GridKitchen:
    width, height = 11, 7
    mug, destination = (2, 3), (9, 3)

    def __init__(self):
        self.position = (1, 3)
        self.walls = {(5, y) for y in range(7) if y not in (1, 3, 5)}
        self.blocked = set()
        self.holding = False
        self.complete = False
        self.history = []
        self.revision = 0

    def free(self, position):
        x, y = position
        return (0 <= x < self.width and 0 <= y < self.height
                and position not in self.walls | self.blocked)

    def observe(self):
        actions = ["stop"]
        if not self.complete:
            actions += [name for name, (dx, dy) in MOVES.items()
                        if self.free((self.position[0] + dx, self.position[1] + dy))]
            if self.position == self.mug and not self.holding:
                actions.append("pick_up:mug_1")
            if self.position == self.destination and self.holding:
                actions.append("place:mug_1:table_1")
            actions += ["wait", "replan"]
        target = self.destination if self.holding else self.mug
        return RobotState(
            goal="Deliver the mug to the table; avoid obstacles",
            room="grid kitchen", holding="mug_1" if self.holding else None,
            visible_objects=(
                {"id": "mug_1", "type": "mug", "location":
                 self.destination if self.complete else self.position if self.holding else self.mug},
                {"id": "table_1", "type": "table", "location": self.destination}),
            legal_actions=tuple(actions), history=tuple(self.history[-8:]),
            task_complete=self.complete,
            context={"position": self.position, "target": target,
                     "subgoal": "complete" if self.complete else
                     "deliver mug" if self.holding else "collect mug",
                     "walls": sorted(self.walls), "obstacles": sorted(self.blocked),
                     "size": [self.width, self.height], "revision": self.revision,
                     "coordinates": "x increases east; y increases south"})

    def step(self, action):
        # Validate against fresh state even if the decision used an older observation.
        if action not in self.observe().legal_actions:
            raise ValueError(f"Action no longer executable: {action}")
        result = "ok"
        if action in MOVES:
            dx, dy = MOVES[action]
            self.position = self.position[0] + dx, self.position[1] + dy
        elif action == "pick_up:mug_1":
            self.holding = True
            self.blocked.add((5, 3))
            self.revision += 1
            result = "Mug picked up; central doorway is now blocked"
        elif action == "place:mug_1:table_1":
            self.holding = False
            self.complete = True
            result = "Delivery verified by environment"
        elif action == "replan":
            result = "Observation refreshed; rule-based subgoal unchanged (no LLM planner)"
        self.history.append(f"{action}: {result}")
        return result


class GridBaseline:
    """BFS controller for verifying the sandbox, explicitly not a Jev model."""

    def decide(self, state):
        context = state.context
        start, target = tuple(context["position"]), tuple(context["target"])
        waypoint = context.get("planner", {}).get("waypoint")
        if waypoint is not None and tuple(waypoint) != start:
            target = tuple(waypoint)
        obstacles = {tuple(p) for p in context["walls"] + context["obstacles"]}
        action = "stop"
        if not state.task_complete:
            interactions = [a for a in state.legal_actions if a.startswith(("pick_up:", "place:"))]
            if interactions:
                action = interactions[0]
            else:
                queue, seen = deque([(start, None)]), {start}
                while queue:
                    point, first = queue.popleft()
                    if point == target:
                        action = first or "wait"
                        break
                    for name, (dx, dy) in MOVES.items():
                        nxt = point[0] + dx, point[1] + dy
                        if (0 <= nxt[0] < context["size"][0]
                                and 0 <= nxt[1] < context["size"][1]
                                and nxt not in obstacles and nxt not in seen):
                            seen.add(nxt)
                            queue.append((nxt, first or name))
        return Decision(action=action, action_confidence=1.0,
                        probabilities={a: float(a == action) for a in state.legal_actions},
                        model="BFS baseline (not Jev)")
