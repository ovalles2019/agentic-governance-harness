"""
Live demo server for the Agentic AI Governance benchmark.

Zero third-party dependencies — standard library only — to keep the project's
"no dependencies beyond Python 3.10+" promise and make deploys bulletproof.

Routes:
  GET /                      -> the interactive demo UI
  GET /api/run?threshold=&seed=  -> runs the harness live, returns results JSON
  GET /healthz               -> health check for the platform
  GET /<static asset>        -> CSS/JS/HTML from web/ and the repo root

Run locally:  python app.py    (serves on http://localhost:8000)
On Render:    binds 0.0.0.0:$PORT
"""

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from harness.runner import run

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")

# Files allowed to be served as static assets, mapped to their on-disk location.
STATIC_FILES = {
    "/": os.path.join(WEB, "index.html"),
    "/index.html": os.path.join(WEB, "index.html"),
    "/styles.css": os.path.join(WEB, "styles.css"),
    "/app.js": os.path.join(WEB, "app.js"),
    "/dashboard.html": os.path.join(ROOT, "dashboard.html"),
    "/favicon.svg": os.path.join(WEB, "favicon.svg"),
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _sweep_thresholds() -> list:
    # Mirrors the demo slider: 0.30 .. 1.30 step 0.05.
    return [round(0.30 + 0.05 * i, 2) for i in range(21)]


class Handler(BaseHTTPRequestHandler):
    server_version = "AgovDemo/0.2"

    def _send(self, code: int, body: bytes, content_type: str,
              cache: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if cache:
            self.send_header("Cache-Control", "public, max-age=3600")
        else:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/healthz":
            self._send_json(200, {"status": "ok"})
            return

        if path == "/api/run":
            self._handle_run(parse_qs(parsed.query))
            return

        if path == "/api/sweep":
            self._handle_sweep(parse_qs(parsed.query))
            return

        target = STATIC_FILES.get(path)
        if target and os.path.isfile(target):
            ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
            with open(target, "rb") as f:
                body = f.read()
            cache = path not in ("/", "/index.html")
            self._send(200, body, ctype + ("; charset=utf-8"
                       if ctype.startswith("text/") or "javascript" in ctype
                       or "json" in ctype else ""), cache=cache)
            return

        self._send_json(404, {"error": "not found", "path": path})

    do_HEAD = do_GET

    def _handle_run(self, qs: dict) -> None:
        try:
            threshold = _clamp(float(qs.get("threshold", ["0.6"])[0]), 0.05, 2.0)
            seed = int(float(qs.get("seed", ["7"])[0]))
        except (ValueError, IndexError):
            self._send_json(400, {"error": "invalid threshold or seed"})
            return
        result = run(judge_threshold=round(threshold, 2), judge_seed=seed,
                     write=False, quiet=True)
        self._send_json(200, result)

    def _handle_sweep(self, qs: dict) -> None:
        """Compute the LLM-judge metric curve across the threshold range in a
        single request. Sequential, so the per-action model cache warms once
        (in live mode) instead of firing one model call per threshold."""
        try:
            seed = int(float(qs.get("seed", ["7"])[0]))
        except (ValueError, IndexError):
            self._send_json(400, {"error": "invalid seed"})
            return
        points, mode = [], "simulated"
        for thr in _sweep_thresholds():
            r = run(judge_threshold=thr, judge_seed=seed, write=False, quiet=True)
            mode = r["judge_mode"]
            j = r["metrics"]["llm_judge"]
            points.append({
                "threshold": thr,
                "recall": j["recall"],
                "precision": j["precision"],
                "trip": j["guardrail_trip_rate"],
            })
        self._send_json(200, {"seed": seed, "judge_mode": mode, "points": points})

    def log_message(self, fmt: str, *args) -> None:
        # Compact one-line access log to stdout (captured by Render).
        print(f"{self.address_string()} {fmt % args}")


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Agentic Governance demo serving on http://0.0.0.0:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    main()
