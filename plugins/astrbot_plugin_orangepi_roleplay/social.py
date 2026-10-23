"""Sparse social activity without extra model calls or collected chat images."""

import json
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .policy import GROUPS
from .settings import PASSIVE_ENABLED, STICKERS_ENABLED


class Social:
    def __init__(self, folder, state_path, clock=time.time, rng=None):
        self.folder = Path(folder)
        self.path = Path(state_path)
        self.clock = clock
        self.rng = rng or random.SystemRandom()
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}

    def eligible(self, kind, group):
        if not (PASSIVE_ENABLED if kind == "passive" else STICKERS_ENABLED):
            return False
        now = self.clock()
        local = datetime.fromtimestamp(now, timezone(timedelta(hours=8)))
        if group not in GROUPS or not 10 <= local.hour < 23:
            return False
        entry = self.state.get(kind + ":" + group, {})
        cooldown, cap = (1200, 4) if kind == "passive" else (900, 6)
        if now - entry.get("last", 0) < cooldown:
            return False
        return (
            entry.get("date") != local.date().isoformat() or entry.get("count", 0) < cap
        )

    def reserve(self, kind, group):
        if not self.eligible(kind, group):
            return False
        now = self.clock()
        date = (
            datetime.fromtimestamp(now, timezone(timedelta(hours=8))).date().isoformat()
        )
        entry = self.state.setdefault(kind + ":" + group, {})
        count = entry.get("count", 0) if entry.get("date") == date else 0
        entry.update(last=now, date=date, count=count + 1)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_suffix(".tmp")
        pending.write_text(json.dumps(self.state), encoding="utf-8")
        pending.replace(self.path)
        return True

    def passive_candidate(
        self, group, text, *, targeted=False, quoted=False, media=False
    ):
        if targeted or quoted or media or not self.eligible("passive", group):
            return False
        text = text.strip()
        if (
            not 6 <= len(text) <= 160
            or "@" in text
            or text.startswith(("/", "!", "！", "搜", "搜索", "查一下", "联网"))
        ):
            return False
        return self.rng.random() < 0.03

    def sticker(self, group, text="", *, bubble=False):
        if not self.eligible("sticker", group) or self.rng.random() >= (
            0.3 if bubble else 0.12
        ):
            return None
        # Do not attach a cheerful random reaction to serious or sad messages.
        if any(
            word in text
            for word in (
                "去世",
                "自杀",
                "难过",
                "抑郁",
                "生病",
                "葬礼",
                "救命",
                "受伤",
                "分手",
            )
        ):
            return None
        files = sorted(p for p in self.folder.glob("*.gif") if p.name != "sad.gif")
        if not files:
            return None
        previous = self.state.get("last_sticker")
        choices = [p for p in files if p.name != previous] or files
        chosen = self.rng.choice(choices)
        self.state["last_sticker"] = chosen.name
        if self.reserve("sticker", group):
            return chosen
        return None
