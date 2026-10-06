"""Local web app: home page, play/watch table, and the simulation dashboard.

Pages:  /  (home)   /table   /sim
API:
    GET  /api/state                live table snapshot
    POST /api/new                  {mode: play|watch, bots: [...], stack, sb, bb, ante, hands, blind_up, speed}
    POST /api/action               {action, amount?}
    POST /api/next                 deal the next hand
    POST /api/settings             {reveal?, speed?, auto_next?, paused?}
    POST /api/sim/start            simulation params (see engine.sim.DEFAULTS)
    GET  /api/sim/status           progress, or the finished summary
    POST /api/sim/cancel
    GET  /api/sim/runs             past runs, newest first
    GET  /api/sim/run/<id>         one run's summary
    GET  /download/<id>/<file>     one CSV (or summary.json)
    GET  /download/<id>.zip        every CSV + summary.json
"""

import io
import json
import os
import threading
import time
import zipfile
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

from engine.bots import BUILTINS
from engine.sim import DEFAULTS as SIM_DEFAULTS, run_simulation, list_runs, load_run
from ui.session import Session

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
PAGES = {"/": "home.html", "/table": "table.html", "/sim": "sim.html"}
CTYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
          ".csv": "text/csv", ".json": "application/json", ".zip": "application/zip"}


class SimJob:
    def __init__(self, params: dict):
        self.params = params
        self.cancel = threading.Event()
        self.progress = {"done": 0, "total": params.get("matches", SIM_DEFAULTS["matches"]),
                         "hands": 0, "elapsed": 0.0}
        self.started = time.time()
        self.result: dict | None = None
        self.error: str | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        def prog(done, total, hands, elapsed):
            self.progress = {"done": done, "total": total, "hands": hands, "elapsed": round(elapsed, 1)}
        try:
            self.result = run_simulation(self.params, on_progress=prog, cancel=self.cancel)
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"

    @property
    def running(self):
        return self.thread.is_alive()

    def status(self):
        return {"running": self.running, "progress": self.progress,
                "elapsed": round(time.time() - self.started, 1), "params": self.params,
                "result": self.result, "error": self.error, "cancelling": self.cancel.is_set()}


class App:
    def __init__(self, default_bots: list[str]):
        self.default_bots = default_bots
        self.session: Session | None = None
        self.sim: SimJob | None = None
        self.last_new: dict | None = None

    def new(self, body: dict):
        mode = body.get("mode", "play")
        session = Session(
            mode=mode, bots=body.get("bots") or self.default_bots,
            stack=int(body.get("stack", 20000)), sb=int(body.get("sb", 50)),
            bb=int(body.get("bb", 100)), ante=int(body.get("ante", 0)),
            hands=int(body.get("hands", 500)), speed=float(body.get("speed", 0.7)),
            blind_up=int(body.get("blind_up", 0)))
        if self.session:
            self.session.stop()
        self.session = session
        self.last_new = body

    def start_sim(self, body: dict):
        if self.sim and self.sim.running:
            raise RuntimeError("a simulation is already running")
        keys = ("bots", "matches", "hands", "stack", "sb", "bb", "ante", "blind_up", "seed",
                "log", "csv_detail", "workers")
        params = {k: body[k] for k in keys if k in body and body[k] not in ("", None)}
        for k in ("matches", "hands", "stack", "sb", "bb", "ante", "blind_up", "seed", "workers"):
            if k in params:
                params[k] = int(params[k])
        if not 1 <= params.get("matches", 1) <= 100000:
            raise ValueError("matches must be 1-100000")
        self.sim = SimJob(params)


def run_files(run_id: str) -> tuple[str, list[str]] | None:
    s = load_run(run_id)
    if not s:
        return None
    names = [f["name"] for f in s.get("files", [])] + ["summary.json"]
    return s["dir"], names


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, data: bytes, ctype: str, code=200, headers=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj, code=200):
            self._send(json.dumps(obj).encode(), "application/json", code)

        def _file(self, path, download_name=None):
            with open(path, "rb") as f:
                data = f.read()
            ctype = CTYPES.get(os.path.splitext(path)[1], "application/octet-stream") + "; charset=utf-8"
            headers = {"Content-Disposition": f'attachment; filename="{download_name}"'} if download_name else None
            self._send(data, ctype, headers=headers)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/state":
                if not app.session:
                    return self._json({"status": "no_game", "builtins": list(BUILTINS),
                                       "default_bots": app.default_bots})
                st = app.session.state()
                st["last_new"] = app.last_new
                return self._json(st)
            if path == "/api/info":
                s = app.session
                return self._json({
                    "builtins": list(BUILTINS), "default_bots": app.default_bots,
                    "sim_defaults": {k: v for k, v in SIM_DEFAULTS.items() if k != "out"},
                    "game": None if not s else {"mode": s.mode, "finished": s.finished is not None,
                                                "hands": s.hands_done},
                    "sim_running": bool(app.sim and app.sim.running),
                })
            if path == "/api/sim/status":
                return self._json(app.sim.status() if app.sim else {"running": False})
            if path == "/api/sim/runs":
                return self._json(list_runs())
            if path.startswith("/api/sim/run/"):
                s = load_run(path.rsplit("/", 1)[1])
                return self._json(s) if s else self._json({"error": "not found"}, 404)
            if path.startswith("/download/"):
                return self._download(path[len("/download/"):])
            f = os.path.join(STATIC, PAGES[path]) if path in PAGES else \
                os.path.normpath(os.path.join(STATIC, path.lstrip("/")))
            if not f.startswith(STATIC) or not os.path.isfile(f):
                return self.send_error(404)
            self._file(f)

        def _download(self, rest: str):
            if rest.endswith(".zip"):
                run_id = rest[:-4]
                found = run_files(run_id)
                if not found:
                    return self.send_error(404)
                run_dir, names = found
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                    for name in names:
                        p = os.path.join(run_dir, name)
                        if os.path.isfile(p):
                            z.write(p, arcname=f"jackten_sim_{run_id}/{name}")
                return self._send(buf.getvalue(), "application/zip",
                                  headers={"Content-Disposition": f'attachment; filename="jackten_sim_{run_id}.zip"'})
            run_id, _, name = rest.partition("/")
            found = run_files(run_id)
            if not found or name not in found[1]:
                return self.send_error(404)
            p = os.path.join(found[0], name)
            if not os.path.isfile(p):
                return self.send_error(404)
            self._file(p, download_name=f"{run_id}_{name}")

        def do_POST(self):
            path = self.path.split("?")[0]
            try:
                body = self._body()
                s = app.session
                if path == "/api/new":
                    app.new(body)
                elif path == "/api/sim/start":
                    app.start_sim(body)
                elif path == "/api/sim/cancel":
                    if app.sim:
                        app.sim.cancel.set()
                elif not s:
                    return self._json({"error": "no game"}, 400)
                elif path == "/api/action":
                    if s.request is None:
                        return self._json({"error": "not your turn"}, 409)
                    resp = {"type": "action_response", "action": body.get("action")}
                    if body.get("amount") is not None:
                        resp["amount"] = int(body["amount"])
                    s.human.inbox.put(resp)
                elif path == "/api/next":
                    s.next_hand.set()
                elif path == "/api/settings":
                    if "reveal" in body:
                        s.reveal = bool(body["reveal"])
                    if "speed" in body:
                        s.speed = float(body["speed"])
                    if "auto_next" in body:
                        s.auto_next = bool(body["auto_next"])
                        if s.auto_next:
                            s.next_hand.set()
                    if "paused" in body:
                        s.set_paused(bool(body["paused"]))
                    s.bump()
                else:
                    return self._json({"error": "unknown endpoint"}, 404)
                return self._json({"ok": True})
            except Exception as e:
                return self._json({"error": f"{e}"}, 400)

    return Handler


def serve(host: str, port: int, default_bots: list[str]):
    app = App(default_bots)
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    return app, httpd
