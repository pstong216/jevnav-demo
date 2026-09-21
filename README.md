# JevNav Demo

JevNav is a small proof of concept for using [TypeSafe Jev](https://typesafe.ai/)
as a fast, probabilistic reflex layer for embodied agents.

The central split is:

- Jev chooses a **high-level skill** such as `navigate_to:mug_1` or
  `pick_up:mug_1` and simultaneously estimates safety, completion, and whether
  a stronger planner is needed.
- A simulator or conventional controller handles geometry, collision checking,
  and low-level motion.

This repository defaults to a deterministic mock environment and mock decision
engine, so it runs without credentials or robot hardware. The real Jev adapter
and an AI2-THOR adapter are included behind optional dependencies.

## Architecture

```text
Natural-language goal
        |
Environment state + legal high-level skills
        |
   Jev reflex decision
     /             \
high confidence    low confidence / unsafe
     |                    |
execute skill       stop or planner fallback
     |
new environment state -> repeat
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
jevnav --engine mock
```

The mock episode executes: navigate to mug -> pick up mug -> navigate to sink ->
place mug in sink -> stop.

### Use the real Jev API

Get an API key from TypeSafe, then:

```bash
pip install -e '.[jev]'
export TYPESAFE_API_KEY='...'
jevnav --engine jev
```

The adapter sends one `Choice` and three `Noul` questions in the same
`system_one` request:

- Which legal high-level skill should run next?
- Is the proposed action unsafe?
- Does this situation require a stronger planner?
- Is the task complete?

No API key is stored by the project.

### Install AI2-THOR

```bash
pip install -e '.[thor]'
```

`AI2ThorAdapter` currently exposes simulator metadata and a compact set of
discrete motions. Connecting semantic skills such as `navigate_to:<object_id>`
to a shortest-path controller is the next milestone.

## Run tests

```bash
pytest
ruff check .
```

## MVP roadmap

- [x] Typed environment state and action contract
- [x] Batched Jev decision: action + safety + escalation + completion
- [x] Confidence/safety gate
- [x] Fully runnable mock kitchen episode
- [x] Optional AI2-THOR state adapter
- [ ] AI2-THOR semantic navigation controller
- [ ] Strong-LLM planner fallback
- [ ] Live dashboard with latency, cost, confidence, and trajectory
- [ ] Evaluation: Jev vs LLM vs hybrid

## Why high-level actions?

Jev is a hosted decision API, not a motor controller. It should select semantic
skills at a modest frequency; a local controller should still produce wheel
velocities, joint commands, paths, and collision-free trajectories.

