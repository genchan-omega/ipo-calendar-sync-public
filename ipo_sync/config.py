"""Settings read from environment variables (GitHub Actions secrets / variables). Empty means default."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

DEFAULT_TITLE_PREFIX = "【IPOブックビル期間】"
DEFAULT_COLOR_ID = "5"  # Google Calendar event color "Banana" (yellow)
DEFAULT_REMINDERS = "prev@19:00,30"
DEFAULT_SHOW_AS = "free"


def _env(name: str, default: str) -> str:
    v = os.environ.get(name, "").strip()
    return v if v else default


@dataclass
class Config:
    title_prefix: str = DEFAULT_TITLE_PREFIX
    color_id: str = DEFAULT_COLOR_ID  # "none" -> calendar default color
    reminders: str = DEFAULT_REMINDERS
    show_as: str = DEFAULT_SHOW_AS  # "free" or "busy"

    @classmethod
    def from_env(cls) -> "Config":
        c = cls(
            title_prefix=_env("IPO_TITLE_PREFIX", DEFAULT_TITLE_PREFIX),
            color_id=_env("IPO_COLOR_ID", DEFAULT_COLOR_ID),
            reminders=_env("IPO_REMINDERS", DEFAULT_REMINDERS),
            show_as=_env("IPO_SHOW_AS", DEFAULT_SHOW_AS).lower(),
        )
        c.validate()
        return c

    def validate(self) -> None:
        if self.color_id != "none" and not (self.color_id.isdigit() and 1 <= int(self.color_id) <= 11):
            raise ValueError(f"IPO_COLOR_ID must be 1-11 or 'none': {self.color_id!r}")
        if self.show_as not in ("free", "busy"):
            raise ValueError(f"IPO_SHOW_AS must be 'free' or 'busy': {self.show_as!r}")
        reminder_minutes(self.reminders, "2026-01-01T00:00:00+09:00")  # raises on bad syntax


def reminder_minutes(spec: str, start_iso: str) -> list[int]:
    """Turn a reminder spec into "minutes before start" values.

    Tokens (comma separated):
      - "30"         -> 30 minutes before the start
      - "prev@19:00" -> 19:00 on the day before the start day
      - "none"       -> no reminders
    """
    from datetime import datetime

    if spec.strip().lower() == "none":
        return []
    start = datetime.fromisoformat(start_iso)
    out: list[int] = []
    for tok in (t.strip() for t in spec.split(",") if t.strip()):
        if tok.isdigit():
            out.append(int(tok))
            continue
        m = re.fullmatch(r"prev@(\d{1,2}):(\d{2})", tok)
        if not m or int(m[1]) > 23 or int(m[2]) > 59:
            raise ValueError(f"bad IPO_REMINDERS token: {tok!r}")
        # minutes from (previous day HH:MM) to start = (24*60 - HH:MM) + start minutes-of-day
        out.append(24 * 60 - (int(m[1]) * 60 + int(m[2])) + start.hour * 60 + start.minute)
    if len(out) > 5:
        raise ValueError("Google Calendar allows at most 5 reminders")
    return out
