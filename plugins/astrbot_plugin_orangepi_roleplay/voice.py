"""Context-matched prerecorded voices with persistent attempt limits."""

import json
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .policy import GROUPS
from .settings import VOICE_ENABLED

COMMANDS = frozenset({"来句语音", "发条语音", "说句语音"})


class VoicePack:
    def __init__(self, folder, state_path, clock=time.time, rng=None):
        self.folder = Path(folder)
        self.path = Path(state_path)
        self.clock = clock
        self.rng = rng or random.SystemRandom()
        config = self.folder / "config.json"
        self.config = (
            json.loads(config.read_text(encoding="utf-8")) if config.is_file() else {}
        )
        self.state = (
            json.loads(self.path.read_text(encoding="utf-8"))
            if self.path.is_file()
            else {}
        )

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_suffix(".tmp")
        pending.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
        pending.replace(self.path)

    def pick(self, group, text="", *, bubble=False):
        local = datetime.fromtimestamp(self.clock(), timezone(timedelta(hours=8)))
        if (
            not VOICE_ENABLED
            or group not in GROUPS
            or not self.config.get("enabled")
            or not 10 <= local.hour < 23
        ):
            return None
        date = local.date().isoformat()
        entry = self.state.get(group, {})
        if self.clock() - entry.get("last", 0) < 1800 or (
            entry.get("date") == date and entry.get("count", 0) >= 3
        ):
            return None
        explicit = text in COMMANDS
        normalized = text.strip(" ?？!！。，")
        choices = [
            item
            for item in self.config.get("clips", [])
            if (bubble and item.get("bubble"))
            or (not bubble and (explicit or normalized in item.get("triggers", [])))
        ]
        valid = []
        for item in choices:
            path = (self.folder / item["file"]).resolve()
            if (
                path.is_relative_to(self.folder.resolve())
                and path.is_file()
                and 0 < item["seconds"] <= 8
            ):
                valid.append((item, path))
        if not valid or (
            not explicit and self.rng.random() >= (0.2 if bubble else 0.25)
        ):
            return None
        choices = [
            pair for pair in valid if pair[0]["file"] != entry.get("clip")
        ] or valid
        item, path = self.rng.choice(choices)
        count = entry.get("count", 0) if entry.get("date") == date else 0
        credit = entry.get("credited_date") != date
        self.state[group] = dict(
            entry,
            date=date,
            count=count + 1,
            last=self.clock(),
            clip=item["file"],
            status="reserved",
        )
        self.save()
        return {
            "path": path,
            "text": item["text"],
            "credit": self.config["attribution"] if credit else None,
        }

    def credited(self, group):
        self.state[group]["credited_date"] = self.state[group]["date"]
        self.save()

    def receipt(self, group, status):
        self.state[group]["status"] = status
        self.save()
