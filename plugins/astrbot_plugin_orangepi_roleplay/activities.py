"""Local keyword replies and restart-safe, sparse group messages."""

import json
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .policy import GROUPS

BEIJING = timezone(timedelta(hours=8))


class Activities:
    def __init__(self, config, state_path, clock=time.time, rng=None):
        self.config = config
        self.state_path = Path(state_path)
        self.clock = clock
        self.rng = rng or random.SystemRandom()
        self.state = {}
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        now = self.clock()
        for group in sorted(GROUPS):
            self.state.setdefault(
                group, {"next_due": now + self.interval(), "date": "", "count": 0}
            )
        self.save()

    def interval(self):
        low, high = self.config["bubbles"]["interval_seconds"]
        # A bad config must not turn the timer into a chat flood.
        return self.rng.uniform(max(5400, low), max(5400, low, high))

    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temp.replace(self.state_path)

    def keyword(self, text):
        return self.config.get("keywords", {}).get(text.strip())

    def due(self):
        now = self.clock()
        cfg = self.config["bubbles"]
        local = datetime.fromtimestamp(now, BEIJING)
        start, end = cfg["hours_beijing"]
        if not cfg["enabled"] or not start <= local.hour < end:
            return []
        return [
            group
            for group in sorted(GROUPS)
            if now >= self.state[group]["next_due"]
            and (
                self.state[group]["date"] != local.date().isoformat()
                or self.state[group]["count"] < min(3, cfg["max_per_group_day"])
            )
        ]

    def reserve(self, group):
        # Count attempts BEFORE the external action. An ambiguous timeout must
        # never cause an immediate resend, including after process restart.
        if group not in self.due():
            return None
        now = self.clock()
        entry = self.state[group]
        date = datetime.fromtimestamp(now, BEIJING).date().isoformat()
        if entry["date"] != date:
            entry.update(date=date, count=0)
        choices = [
            s
            for s in self.config["bubbles"]["texts"]
            if isinstance(s, str) and 1 <= len(s) <= 2 and s != entry.get("text")
        ]
        if not choices:
            return None
        text = self.rng.choice(choices)
        entry.update(
            count=entry["count"] + 1,
            next_due=now + self.interval(),
            attempted_at=now,
            text=text,
            status="pending",
        )
        self.save()
        return text

    def receipt(self, group, status, message_id=None):
        self.state[group].update(status=status, message_id=message_id)
        self.save()
