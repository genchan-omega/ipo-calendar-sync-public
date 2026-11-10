"""Register IPO book-building periods in Google Calendar.

Duplicates are detected by a dedupe key (in the description or a private extended property).
Existing events are never modified or deleted.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .config import Config, reminder_minutes
from .sbi import JST, SBI_URL, Ipo

API = "https://www.googleapis.com/calendar/v3"


def title(ipo: Ipo, cfg: Config) -> str:
    return f"{cfg.title_prefix}{ipo.name}"


def _d(s: str | None) -> str:
    return datetime.fromisoformat(s).strftime("%Y/%-m/%-d") if s else "記載なし"


def _dt(s: str) -> str:
    return datetime.fromisoformat(s).strftime("%Y/%-m/%-d %-H:%M")


def description(ipo: Ipo) -> str:
    return (
        "SBI証券の公開IPO情報に基づくブックビルディング期間。\n"
        f"期間: {_dt(ipo.bb_start)}〜{_dt(ipo.bb_end)}\n"
        f"銘柄コード: {ipo.code}（{ipo.market}）\n"
        f"仮条件決定日: {_d(ipo.price_decision_date)}\n"
        f"発行価格決定日（抽選日）: {_d(ipo.lottery_date)}\n"
        f"上場予定日: {_d(ipo.listing_date)}\n"
        f"重複確認キー: {ipo.dedupe_key()}\n"
        f"出典: {SBI_URL}"
    )


def event_body(ipo: Ipo, cfg: Config) -> dict:
    body = {
        "summary": title(ipo, cfg),
        "description": description(ipo),
        "start": {"dateTime": ipo.bb_start, "timeZone": "Asia/Tokyo"},
        "end": {"dateTime": ipo.bb_end, "timeZone": "Asia/Tokyo"},
        "transparency": "transparent" if cfg.show_as == "free" else "opaque",
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": m} for m in reminder_minutes(cfg.reminders, ipo.bb_start)],
        },
        "extendedProperties": {"private": {"ipoDedupeKey": ipo.dedupe_key()}},
    }
    if cfg.color_id != "none":
        body["colorId"] = cfg.color_id
    return body


@dataclass
class Result:
    created: list[str] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)
    past: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)  # same title, different dates: reported, not modified


class CalendarClient:
    """Minimal Google Calendar REST client authenticated as a service account."""

    def __init__(self, calendar_id: str, session) -> None:
        self.calendar_id = calendar_id
        self.s = session

    @classmethod
    def from_env(cls) -> "CalendarClient":
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account

        info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/calendar.events"]
        )
        return cls(os.environ["GOOGLE_CALENDAR_ID"], AuthorizedSession(creds))

    def list_between(self, time_min: str, time_max: str) -> list[dict]:
        out: list[dict] = []
        token = None
        while True:
            params = {"timeMin": time_min, "timeMax": time_max, "singleEvents": "true", "maxResults": 250}
            if token:
                params["pageToken"] = token
            r = self.s.get(f"{API}/calendars/{self.calendar_id}/events", params=params, timeout=30)
            r.raise_for_status()
            j = r.json()
            out += j.get("items", [])
            token = j.get("nextPageToken")
            if not token:
                return out

    def insert(self, body: dict) -> dict:
        # No conferenceDataVersion -> no Google Meet link is created.
        r = self.s.post(
            f"{API}/calendars/{self.calendar_id}/events", params={"sendUpdates": "none"}, json=body, timeout=30
        )
        r.raise_for_status()
        return r.json()

    def delete(self, event_id: str) -> None:
        r = self.s.delete(
            f"{API}/calendars/{self.calendar_id}/events/{event_id}", params={"sendUpdates": "none"}, timeout=30
        )
        r.raise_for_status()


def sync(client, ipos: list[Ipo], cfg: Config | None = None, now: datetime | None = None,
         dry_run: bool = False) -> Result:
    cfg = cfg or Config()
    now = now or datetime.now(JST)
    res = Result()
    for ipo in ipos:
        label = f"{ipo.name} ({ipo.code})"
        start = datetime.fromisoformat(ipo.bb_start)
        end = datetime.fromisoformat(ipo.bb_end)
        if end <= now:
            res.past.append(label)
            continue
        near = client.list_between((start - timedelta(days=3)).isoformat(), (end + timedelta(days=3)).isoformat())
        key = ipo.dedupe_key()
        if any(key in (e.get("description") or "") for e in near) or any(
            e.get("extendedProperties", {}).get("private", {}).get("ipoDedupeKey") == key for e in near
        ):
            res.existing.append(label)
            continue
        if any(e.get("summary") == title(ipo, cfg) for e in near):
            res.changed.append(label)
            continue
        if not dry_run:
            client.insert(event_body(ipo, cfg))
        res.created.append(label)
    return res


def selftest(client) -> str:
    """Check write access: create a test event far in the future, read it back, always delete it."""
    body = {
        "summary": "[ipo-calendar-sync write test - auto deleted]",
        "start": {"dateTime": "2030-01-01T03:00:00+09:00", "timeZone": "Asia/Tokyo"},
        "end": {"dateTime": "2030-01-01T03:30:00+09:00", "timeZone": "Asia/Tokyo"},
        "transparency": "transparent",
        "reminders": {"useDefault": False, "overrides": []},
    }
    created = client.insert(body)
    try:
        found = client.list_between("2030-01-01T00:00:00+09:00", "2030-01-02T00:00:00+09:00")
        ok = any(e.get("id") == created["id"] for e in found)
    finally:
        client.delete(created["id"])
    return "created, read back and deleted a test event" if ok else "created a test event but could not read it back (deleted)"


def configured() -> bool:
    return bool(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") and os.environ.get("GOOGLE_CALENDAR_ID"))
