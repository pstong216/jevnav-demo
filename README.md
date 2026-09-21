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

### Interactive navigation demo (new)

```bash
pip install -e .
jevnav-dashboard
```

Open http://127.0.0.1:8765. Click **自动运行** or **执行一步**.
The robot collects a mug, the central doorway becomes blocked, and it must
deliver the mug via another doorway. The dashboard shows the grid, subgoal,
candidate actions, selected action, measured decision latency, and execution
results. **导出日志** downloads the current episode as JSON.

The default engine is a deterministic **BFS baseline, not Jev**. This is a
fully observed 2D grid sandbox, not AI2-THOR, visual navigation, or robot physics.
Candidates are generated from current collision and interaction preconditions;
the executor validates them again before moving. Completion is checked by the
environment, not a model's completion score. Episodes stop after 100 actions.
Subgoals are rule-based; asynchronous LLM planning is not implemented yet.

To use the existing Jev SDK adapter for these same live grid states:

```bash
pip install -e '.[jev]'
export TYPESAFE_API_KEY='...'
jevnav-dashboard --engine jev
```

The API adapter is not yet validated end-to-end with live credentials. API errors
stop the episode; they never silently switch to the baseline. Keys remain in the
server process. The server binds only to localhost and supports one shared session.
In this sandbox, `replan` refreshes observations; it does not call an LLM.

Architecture inspiration: [rmalde/minecraft-agent](https://github.com/rmalde/minecraft-agent),
particularly executable candidates and action-result feedback. No source code
from that project is copied.

### Original mock CLI

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
- Is the state risky for the most appropriate next action? This is a heuristic
  signal, not a safety assessment conditioned on the selected answer: concurrent
  questions do not see each other's outputs.
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
- [x] Interactive 2D grid with dynamic obstacle, executable actions and episode export
- [ ] AI2-THOR semantic navigation controller
- [ ] Strong-LLM planner fallback
- [x] Local dashboard with decision latency, action history and map
- [ ] API cost accounting and calibrated confidence visualization
- [ ] Evaluation: Jev vs LLM vs hybrid

## Why high-level actions?

Jev is a hosted decision API, not a motor controller. It should select semantic
skills at a modest frequency; a local controller should still produce wheel
velocities, joint commands, paths, and collision-free trajectories.
