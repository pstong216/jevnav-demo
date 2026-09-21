from concurrent.futures import Future
from dataclasses import replace
import math
import unittest

from jevnav.api import APIError
from jevnav.dashboard import Session
from jevnav.decision import TypeSafeJevEngine
from jevnav.grid import GridBaseline, GridKitchen
from jevnav.models import Decision
from jevnav.planner import BackgroundPlanner, OpenRouterPlanner, RulePlanner


class ManualExecutor:
    def __init__(self):
        self.requests = []

    def submit(self, fn, state):
        future = Future()
        self.requests.append((future, fn, state))
        return future

    def finish(self):
        future, fn, state = self.requests[-1]
        future.set_result(fn(state))

    def shutdown(self, **kwargs):
        pass


def response_for(payload, action):
    criteria = payload["questions"]["next_action"]["criteria"]
    answers = {k: {"type": "noul", "noul": 0.0} for k in payload["questions"]}
    answers["next_action"] = {"type": "choice", "choice": action, "confidence": 0.91,
                              "probabilities": {a: float(a == action) for a in criteria}}
    return {"model": "fixture-only", "answers": answers,
            "usage": {"input_tokens": 42, "output_tokens": 12}}


class IntegrationTests(unittest.TestCase):
    def test_jev_request_and_selected_action_risk(self):
        state = GridKitchen().observe()
        def transport(url, key, payload):
            self.assertEqual(url, "https://api.typesafe.ai/v1/systemone")
            self.assertEqual(key, "test-key")
            self.assertEqual(payload["model"], "jev-latest")
            result = response_for(payload, "move:east")
            for i, action in enumerate(state.legal_actions):
                self.assertIn(action, payload["questions"][f"risk_{i}"]["instructions"])
                result["answers"][f"risk_{i}"]["noul"] = 0.8 if action == "move:east" else 0.1
            return result
        decision = TypeSafeJevEngine("test-key", transport=transport).decide(state)
        self.assertEqual(decision.unsafe_probability, 0.8)
        self.assertEqual(decision.usage["input_tokens"], 42)

    def test_invalid_api_values_fail_closed(self):
        state = GridKitchen().observe()
        for field, value in (("choice", "fly"), ("confidence", math.nan),
                             ("confidence", 1.2), ("probabilities", {"stop": 1})):
            def transport(url, key, payload):
                result = response_for(payload, "move:east")
                result["answers"]["next_action"][field] = value
                return result
            with self.subTest(field=field, value=value), self.assertRaises(APIError):
                TypeSafeJevEngine("test-key", transport=transport).decide(state)

    def test_api_failure_does_not_execute_baseline(self):
        def fail(*args):
            raise APIError("API HTTP 401")
        session = Session(TypeSafeJevEngine("test-key", transport=fail), "jev")
        with self.assertRaises(APIError):
            session.step()
        self.assertEqual(session.env.position, (1, 3))
        self.assertEqual(session.events, [])

    def test_stale_plan_after_stage_change_and_reset(self):
        executor = ManualExecutor()
        planner = BackgroundPlanner(RulePlanner(), executor)
        env = GridKitchen()
        planner.tick(env.observe(), 0)
        planner.tick(env.observe(), 0)
        self.assertEqual(len(executor.requests), 1)
        env.step("move:east")
        env.step("pick_up:mug_1")
        executor.finish()
        planner.tick(env.observe(), 2)
        self.assertIsNone(planner.current)
        self.assertEqual(planner.events[0]["event"], "discarded_stale_plan")
        planner.reset()
        executor.finish()
        planner.tick(env.observe(), 2)
        self.assertIsNone(planner.current)
        executor.finish()
        planner.tick(env.observe(), 2)
        self.assertEqual(planner.current.objective, "deliver mug")

    def test_planner_failure_and_invalid_waypoint(self):
        state = GridKitchen().observe()
        for content in ('{"objective":"go","waypoint":[5,0]}', 'not json'):
            planner = OpenRouterPlanner("test-model", "test-key", transport=lambda *args:
                {"choices": [{"message": {"content": content}}]})
            with self.assertRaises(APIError):
                planner.plan(state)
        executor = ManualExecutor()
        background = BackgroundPlanner(RulePlanner(), executor)
        background.tick(state, 0)
        executor.requests[0][0].set_exception(APIError("test"))
        background.tick(state, 0)
        self.assertIsNotNone(background.error)
        self.assertIsNone(background.current)

    def test_planner_guidance_is_consumed_by_controller(self):
        state = GridKitchen().observe()
        state = replace(state, context={**state.context, "planner": {"waypoint": [1, 0]}})
        self.assertEqual(GridBaseline().decide(state).action, "move:north")

    def test_full_episode_with_planner_and_fixture_api(self):
        session = None
        def transport(url, key, payload):
            action = GridBaseline().decide(session.observe()).action
            self.assertIn("planner", payload["state"])
            return response_for(payload, action)
        session = Session(TypeSafeJevEngine("test-key", transport=transport), "fixture", RulePlanner())
        session.planner.close()
        executor = ManualExecutor()
        session.planner = BackgroundPlanner(RulePlanner(), executor)
        try:
            for _ in range(60):
                if session.planner.pending:
                    executor.finish()
                snapshot = session.step()
                if snapshot["finished"]:
                    break
            self.assertEqual(snapshot["finish_reason"], "delivery_verified")
            self.assertEqual(snapshot["metrics"]["jev_input_tokens"], 42*14)
            self.assertTrue(any(e["event"] == "plan_ready" for e in snapshot["planner"]["events"]))
        finally:
            session.close()

    def test_replan_without_planner_stops(self):
        class Engine:
            def decide(self, state):
                return Decision("replan", 1)
        session = Session(Engine(), "test")
        self.assertTrue(session.step()["finished"])
        self.assertEqual(session.env.position, (1, 3))


if __name__ == "__main__":
    unittest.main()
