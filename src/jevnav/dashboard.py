"""Local single-session dashboard. API keys stay in the Python process."""
import argparse
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import time

from .decision import TypeSafeJevEngine
from .grid import GridBaseline, GridKitchen
from .policy import ReflexPolicy
from .api import APIError
from .planner import BackgroundPlanner, OpenRouterPlanner, RulePlanner


class Session:
    def __init__(self, engine, name, planner=None):
        self.policy = ReflexPolicy(engine)
        self.name = name
        self.planner = BackgroundPlanner(planner) if planner else None
        self.reset()

    def reset(self):
        self.env = GridKitchen()
        self.events = []
        self.finished = False
        self.finish_reason = None
        self.no_progress = 0
        if self.planner:
            self.planner.reset()

    def observe(self):
        state = self.env.observe()
        if self.planner and self.planner.current:
            state = replace(state, context={**state.context,
                            "planner": asdict(self.planner.current)})
        return state

    def snapshot(self):
        return {"state": asdict(self.observe()), "events": self.events,
                "engine": self.name, "finished": self.finished,
                "finish_reason": self.finish_reason,
                "planner": self.planner.snapshot() if self.planner else {"enabled": False},
                "metrics": {"steps": len(self.events),
                            "decision_ms": round(sum(e["latency_ms"] for e in self.events), 1),
                            "jev_input_tokens": sum(e["decision"]["usage"].get("input_tokens", 0)
                                                    for e in self.events)}}

    def step(self):
        if self.finished:
            return self.snapshot()
        if self.planner:
            self.planner.tick(self.env.observe(), len(self.events))
            if self.planner.error:
                self.finished = True
                self.finish_reason = self.planner.error
                return self.snapshot()
            if not self.planner.current:
                return self.snapshot()  # Await initial/new-stage plan; do not fabricate an action.
        before = self.observe()
        started = time.perf_counter()
        decision = self.policy.act(before)
        latency = round((time.perf_counter() - started) * 1000, 1)
        previous = (self.env.position, self.env.holding, self.env.complete)
        result = self.env.step(decision.action)
        if decision.action == "replan":
            if self.planner:
                self.planner.force = True
                result = "Background replan requested"
            else:
                result = "No planner configured; stopped instead of repeating replan"
                self.finished = True
                self.finish_reason = result
        self.no_progress = (self.no_progress + 1 if previous ==
                            (self.env.position, self.env.holding, self.env.complete) else 0)
        self.events.append({"step": len(self.events) + 1,
                            "candidates": before.legal_actions,
                            "decision": asdict(decision), "latency_ms": latency,
                            "result": result, "position": self.env.position,
                            "context": before.context})
        if self.env.complete:
            self.finish_reason = "delivery_verified"
        elif decision.action == "stop":
            self.finish_reason = "policy_stopped"
        elif self.no_progress >= 12:
            self.finish_reason = "no_progress_12_steps"
        elif len(self.events) >= 100:
            self.finish_reason = "step_limit"
        self.finished = self.finish_reason is not None
        if self.planner:
            # Invalidate old-stage plans immediately after pickup/placement.
            self.planner.tick(self.env.observe(), len(self.events))
        return self.snapshot()

    def close(self):
        if self.planner:
            self.planner.close()


def handler_for(session):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, value, status=200):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/api/state":
                return self.respond(session.snapshot())
            if self.path != "/":
                return self.respond({"error": "Not found"}, 404)
            body = Path(__file__).with_name("dashboard.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            # Custom header blocks cross-origin form submissions; no CORS enabled.
            if self.headers.get("X-JevNav") != "1":
                return self.respond({"error": "Missing request header"}, 403)
            try:
                if self.path == "/api/reset":
                    session.reset()
                    return self.respond(session.snapshot())
                if self.path == "/api/step":
                    return self.respond(session.step())
                self.respond({"error": "Not found"}, 404)
            except Exception as exc:
                # Avoid exposing upstream response bodies or credentials in the browser.
                session.finished = True
                session.finish_reason = str(exc) if isinstance(exc, APIError) else "Decision/execution failed"
                self.respond({"error": session.finish_reason}, 500)
    return Handler


def main():
    parser = argparse.ArgumentParser(description="Local JevNav navigation dashboard")
    parser.add_argument("--engine", choices=("baseline", "jev"), default="baseline")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--planner", choices=("none", "rule", "llm"), default="none")
    parser.add_argument("--planner-model", help="OpenRouter model ID supporting JSON mode")
    args = parser.parse_args()
    try:
        engine = TypeSafeJevEngine() if args.engine == "jev" else GridBaseline()
        planner = (OpenRouterPlanner(args.planner_model) if args.planner == "llm" else
                   RulePlanner() if args.planner == "rule" else None)
    except APIError as exc:
        parser.error(str(exc))
    session = Session(engine, args.engine, planner)
    server = HTTPServer(("127.0.0.1", args.port), handler_for(session))
    print(f"JevNav: http://127.0.0.1:{args.port} | engine={args.engine}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        session.close()


if __name__ == "__main__":
    main()
