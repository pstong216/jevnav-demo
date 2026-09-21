from jevnav.decision import MockDecisionEngine
from jevnav.environment import MockKitchenEnvironment
from jevnav.models import Decision, RobotState
from jevnav.policy import ReflexPolicy


def test_mock_episode_completes() -> None:
    env = MockKitchenEnvironment()
    policy = ReflexPolicy(MockDecisionEngine())

    for _ in range(10):
        state = env.observe()
        decision = policy.act(state)
        if decision.action == "stop":
            assert state.task_complete
            return
        env.step(decision.action)
    raise AssertionError("episode did not complete")


class UnsafeEngine:
    def decide(self, state: RobotState) -> Decision:
        return Decision(
            action=state.legal_actions[0],
            action_confidence=0.99,
            unsafe_probability=0.95,
            model="unsafe-test",
        )


def test_safety_gate_stops_unsafe_action() -> None:
    state = MockKitchenEnvironment().observe()
    decision = ReflexPolicy(UnsafeEngine()).act(state)
    assert decision.action == "stop"
    assert decision.model.endswith("+gate")


class LowConfidenceEngine:
    def decide(self, state: RobotState) -> Decision:
        return Decision(action=state.legal_actions[0], action_confidence=0.1)


def test_low_confidence_routes_to_replan() -> None:
    state = MockKitchenEnvironment().observe()
    decision = ReflexPolicy(LowConfidenceEngine()).act(state)
    assert decision.action == "replan"

