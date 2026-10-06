"""Bot adapters.

Every player — built-in, external program, or the human in the UI — sits behind
the same interface, and only ever sees protocol messages from its own seat's
point of view:

    notify(msg)          every broadcast message (match_start, hand_start, ...)
    act(msg, timeout)    an action_request; returns an action_response dict

Bot specs accepted by make_bot():
    random | caller | raiser | folder        built-ins
    cmd:<command line>                       external NDJSON program, e.g.
                                             cmd:python bots/random_bot.py
    py:<module>:<Class>                      in-process Python class
"""

import importlib
import json
import queue
import random
import shlex
import subprocess
import sys
import threading


class BotError(Exception):
    pass


class BotTimeout(BotError):
    pass


class Bot:
    name = "bot"

    def notify(self, msg: dict) -> None:
        pass

    def act(self, msg: dict, timeout: float | None = None) -> dict:
        raise NotImplementedError

    def close(self) -> None:
        pass


def raise_to_for_pot_fraction(req: dict, frac: float) -> int:
    """Total 'raise to' amount for a bet of `frac` x pot after calling."""
    pot_after_call = req["pot"] + req["to_call"]
    target = req["your_bet"] + req["to_call"] + int(frac * pot_after_call)
    return max(req["min_raise_to"], min(target, req["max_raise_to"]))


class RandomBot(Bot):
    """Picks uniformly among legal actions; raise size uniform over a few pot fractions + all-in."""
    name = "random"
    SIZES = (0.33, 0.5, 0.75, 1.0, 2.0, "all_in")

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def act(self, msg, timeout=None):
        action = self.rng.choice(msg["legal_actions"])
        if action != "raise":
            return {"type": "action_response", "action": action}
        size = self.rng.choice(self.SIZES)
        amount = msg["max_raise_to"] if size == "all_in" else raise_to_for_pot_fraction(msg, size)
        return {"type": "action_response", "action": "raise", "amount": amount}


class CallerBot(Bot):
    """Calling station: always check or call."""
    name = "caller"

    def act(self, msg, timeout=None):
        return {"type": "action_response",
                "action": "check" if "check" in msg["legal_actions"] else "call"}


class RaiserBot(Bot):
    """Maniac: raise pot whenever legal, else call."""
    name = "raiser"

    def act(self, msg, timeout=None):
        if "raise" in msg["legal_actions"]:
            return {"type": "action_response", "action": "raise",
                    "amount": raise_to_for_pot_fraction(msg, 1.0)}
        return {"type": "action_response",
                "action": "check" if "check" in msg["legal_actions"] else "call"}


class FolderBot(Bot):
    """Check if free, otherwise fold."""
    name = "folder"

    def act(self, msg, timeout=None):
        return {"type": "action_response",
                "action": "check" if "check" in msg["legal_actions"] else "fold"}


class SubprocessBot(Bot):
    """An external program speaking NDJSON on stdin/stdout. stderr passes through."""

    def __init__(self, command: str, name: str | None = None):
        args = command if sys.platform == "win32" else shlex.split(command)
        self.name = name or command
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, bufsize=1, encoding="utf-8")
        self.lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)  # EOF

    def _send(self, msg):
        try:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise BotError(f"bot process closed: {e}") from e

    def notify(self, msg):
        try:
            self._send(msg)
        except BotError:
            pass  # surfaced on the next act()

    def act(self, msg, timeout=None):
        self._send(msg)
        while True:
            try:
                line = self.lines.get(timeout=timeout)
            except queue.Empty:
                raise BotTimeout(f"no response within {timeout:.1f}s")
            if line is None:
                raise BotError("bot process exited")
            line = line.strip()
            if not line:
                continue
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                continue  # stray print on stdout; ignore
            if isinstance(resp, dict) and resp.get("type") == "action_response":
                return resp

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=2)
        except Exception:
            self.proc.kill()


BUILTINS = {"random": RandomBot, "caller": CallerBot, "raiser": RaiserBot, "folder": FolderBot}


def parse_spec(raw: str) -> tuple[str | None, str]:
    """'label=spec' -> (label, spec); plain 'spec' -> (None, spec)."""
    raw = raw.strip()
    label, sep, spec = raw.partition("=")
    if not sep or label.startswith(("cmd:", "py:")):
        return None, raw
    return label.strip(), spec.strip()


def make_bot(spec: str, rng: random.Random | None = None) -> Bot:
    spec = spec.strip()
    if spec.startswith("cmd:"):
        return SubprocessBot(spec[4:].strip())
    if spec.startswith("py:"):
        module, _, cls = spec[3:].rpartition(":")
        bot = getattr(importlib.import_module(module), cls)()
        bot.name = getattr(bot, "name", cls)
        return bot
    if spec not in BUILTINS:
        raise ValueError(f"unknown bot {spec!r}; choose {', '.join(BUILTINS)}, cmd:..., or py:module:Class")
    cls = BUILTINS[spec]
    return cls(rng) if cls is RandomBot else cls()
