"""Local single-session dashboard. API keys stay in the Python process."""
import argparse
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import time

from .decision import TypeSafeJevEngine
from .grid import GridBaseline, GridKitchen
from .policy import ReflexPolicy


class Session:
    def __init__(self, engine, name):
        self.policy = ReflexPolicy(engine)
        self.name = name
        self.reset()

    def reset(self):
        self.env = GridKitchen()
        self.events = []
        self.finished = False

    def snapshot(self):
        return {"state": asdict(self.env.observe()), "events": self.events,
                "engine": self.name, "finished": self.finished}

    def step(self):
        if self.finished:
            return self.snapshot()
        before = self.env.observe()
        started = time.perf_counter()
        decision = self.policy.act(before)
        latency = round((time.perf_counter() - started) * 1000, 1)
        result = self.env.step(decision.action)
        self.events.append({"step": len(self.events) + 1,
                            "candidates": before.legal_actions,
                            "decision": asdict(decision), "latency_ms": latency,
                            "result": result, "position": self.env.position})
        self.finished = (decision.action == "stop" or self.env.complete
                         or len(self.events) >= 100)
        return self.snapshot()


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
            except Exception:
                # Avoid exposing upstream response bodies or credentials in the browser.
                session.finished = True
                self.respond({"error": "Decision/execution failed; episode stopped. Check API configuration."}, 500)
    return Handler


def main():
    parser = argparse.ArgumentParser(description="Local JevNav navigation dashboard")
    parser.add_argument("--engine", choices=("baseline", "jev"), default="baseline")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    engine = TypeSafeJevEngine() if args.engine == "jev" else GridBaseline()
    server = HTTPServer(("127.0.0.1", args.port), handler_for(Session(engine, args.engine)))
    print(f"JevNav: http://127.0.0.1:{args.port} | engine={args.engine}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
