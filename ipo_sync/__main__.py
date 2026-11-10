"""Fetch the SBI IPO list and register new book-building periods in Google Calendar.

Usage: python -m ipo_sync [--dry-run | --selftest]

Without GOOGLE_SERVICE_ACCOUNT_JSON / GOOGLE_CALENDAR_ID it only fetches and prints the list.
Exits with status 1 on any failure (fetch, parse, configuration or API error).
"""
from __future__ import annotations

import json
import os
import sys

from . import calendar as cal
from .config import Config
from .sbi import ParseError, fetch_html, parse


def _summary(lines: list[str]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def _err(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    try:
        cfg = Config.from_env()
    except ValueError as e:
        return _err(f"invalid configuration: {e}")

    if "--selftest" in sys.argv:
        if not cal.configured():
            return _err("GOOGLE_SERVICE_ACCOUNT_JSON / GOOGLE_CALENDAR_ID are not set")
        try:
            msg = cal.selftest(cal.CalendarClient.from_env())
        except Exception as e:  # noqa: BLE001
            return _err(f"write test failed: {type(e).__name__}: {e}")
        print(msg)
        _summary(["", f"### Write test: {msg}"])
        return 0

    dry_run = "--dry-run" in sys.argv
    skipped: list[str] = []
    try:
        ipos = parse(fetch_html(), skipped=skipped)
    except ParseError as e:
        return _err(str(e))
    print(json.dumps([i.asdict() for i in ipos], ensure_ascii=False, indent=2))
    lines = [f"## SBI IPO list: {len(ipos)}", "", "| Company | Code | Book-building | Listing |", "|---|---|---|---|"]
    lines += [f"| {i.name} | {i.code} | {i.bb_start[:16]} – {i.bb_end[:16]} | {i.listing_date or '-'} |" for i in ipos]
    if skipped:
        lines += ["", f"Skipped (period not decided yet): {', '.join(skipped)}"]
        print(f"skipped (period not decided yet): {', '.join(skipped)}", file=sys.stderr)
    _summary(lines)

    if not cal.configured():
        print("calendar credentials are not set: fetch only", file=sys.stderr)
        _summary(["", "**Calendar credentials are not set (fetch only).**"])
        return 0
    try:
        res = cal.sync(cal.CalendarClient.from_env(), ipos, cfg=cfg, dry_run=dry_run)
    except Exception as e:  # noqa: BLE001 - any failure must end with a non-zero status
        return _err(f"calendar sync failed: {type(e).__name__}: {e}")

    out = ["", f"### Calendar{' (dry run)' if dry_run else ''}"]
    for label, items in (("Created", res.created), ("Already registered", res.existing),
                         ("Already ended", res.past), ("Possible date change (not modified)", res.changed)):
        out.append(f"- {label}: {', '.join(items) if items else 'none'}")
    print("\n".join(out))
    _summary(out)

    notify = os.environ.get("NOTIFY_FILE")
    if notify and not dry_run and (res.created or res.changed):
        with open(notify, "w", encoding="utf-8") as f:
            if res.created:
                f.write("IPO book-building periods added: " + ", ".join(res.created) + "\n")
            if res.changed:
                f.write("Possible date change, please check: " + ", ".join(res.changed) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
