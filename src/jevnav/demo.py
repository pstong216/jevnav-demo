from __future__ import annotations

import argparse
import json
import time

from .decision import MockDecisionEngine, TypeSafeJevEngine
from .environment import MockKitchenEnvironment
from .policy import ReflexPolicy


def run_episode(engine_name: str, max_steps: int = 10) -> int:
    engine = TypeSafeJevEngine() if engine_name == "jev" else MockDecisionEngine()
    policy = ReflexPolicy(engine)
    env = MockKitchenEnvironment()

    print("Goal: Put the mug into the sink\n")
    for step in range(max_steps):
        state = env.observe()
        started = time.perf_counter()
        decision = policy.act(state)
        latency_ms = (time.perf_counter() - started) * 1_000
        print(
            json.dumps(
                {
                    "step": step,
                    "action": decision.action,
                    "confidence": round(decision.action_confidence, 3),
                    "unsafe": round(decision.unsafe_probability, 3),
                    "needs_planner": round(decision.needs_planner_probability, 3),
                    "latency_ms": round(latency_ms, 1),
                    "model": decision.model,
                },
                indent=2,
            )
        )
        if decision.action == "stop":
            success = state.task_complete
            print(f"\nEpisode {'succeeded' if success else 'stopped early'}.")
            return 0 if success else 1
        env.step(decision.action)
    print("\nEpisode exceeded the step limit.")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the JevNav mock kitchen episode")
    parser.add_argument("--engine", choices=("mock", "jev"), default="mock")
    parser.add_argument("--max-steps", type=int, default=10)
    args = parser.parse_args()
    raise SystemExit(run_episode(args.engine, args.max_steps))


if __name__ == "__main__":
    main()

