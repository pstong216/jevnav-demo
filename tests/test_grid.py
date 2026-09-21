import unittest

from jevnav.dashboard import Session
from jevnav.grid import GridBaseline, GridKitchen
from jevnav.models import Decision, RobotState
from jevnav.policy import ReflexPolicy


class GridTests(unittest.TestCase):
    def test_delivery_with_dynamic_obstacle(self):
        session = Session(GridBaseline(), "baseline")
        for _ in range(50):
            snapshot = session.step()
            self.assertNotIn(session.env.position, session.env.walls | session.env.blocked)
            if snapshot["finished"]:
                break
        self.assertTrue(session.env.complete)
        self.assertIn((5, 3), session.env.blocked)
        self.assertTrue(any(e["position"] in ((5, 1), (5, 5)) for e in session.events))
        count = len(session.events)
        session.step()
        self.assertEqual(len(session.events), count)
        session.reset()
        self.assertFalse(session.env.complete)
        self.assertEqual(session.events, [])

    def test_reject_collision_and_invalid_pickup(self):
        env = GridKitchen()
        with self.assertRaises(ValueError):
            env.step("pick_up:mug_1")
        env.position = (4, 3)
        env.blocked.add((5, 3))
        self.assertNotIn("move:east", env.observe().legal_actions)
        with self.assertRaises(ValueError):
            env.step("move:east")
        self.assertEqual(env.position, (4, 3))

    def test_rejected_decision_cannot_fall_through_to_movement(self):
        class Unsafe:
            def decide(self, state):
                return Decision("move:east", 1.0, unsafe_probability=1.0)
        state = RobotState("test", "test", None, (), ("move:east",))
        with self.assertRaises(RuntimeError):
            ReflexPolicy(Unsafe()).act(state)


if __name__ == "__main__":
    unittest.main()
