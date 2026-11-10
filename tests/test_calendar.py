from datetime import datetime

from ipo_sync import calendar as cal
from ipo_sync.config import Config
from ipo_sync.sbi import JST, Ipo

IPO = Ipo("ＮＯＴＡ", "673A", "東証グロース", "2026-11-24T00:00:00+09:00", "2026-11-27T11:00:00+09:00",
          "2026-11-20", "2026-11-30", "2026-12-09")
NOW = datetime(2026, 11, 10, 23, 0, tzinfo=JST)


class Fake:
    def __init__(self, events=()):
        self.events, self.inserted, self.deleted = list(events), [], []

    def list_between(self, a, b):
        return self.events

    def insert(self, body):
        body = dict(body, id=f"e{len(self.inserted)}")
        self.inserted.append(body)
        self.events.append(body)
        return body

    def delete(self, event_id):
        self.deleted.append(event_id)


def test_default_body():
    b = cal.event_body(IPO, Config())
    assert b["summary"] == "【IPOブックビル期間】ＮＯＴＡ"
    assert b["colorId"] == "5" and b["transparency"] == "transparent"
    assert [o["minutes"] for o in b["reminders"]["overrides"]] == [300, 30]
    assert "conferenceData" not in b
    assert IPO.dedupe_key() in b["description"]


def test_custom_body():
    cfg = Config(title_prefix="IPO: ", color_id="none", reminders="none", show_as="busy")
    b = cal.event_body(IPO, cfg)
    assert b["summary"] == "IPO: ＮＯＴＡ"
    assert "colorId" not in b and b["transparency"] == "opaque"
    assert b["reminders"]["overrides"] == []


def test_creates_when_missing():
    c = Fake()
    assert cal.sync(c, [IPO], now=NOW).created and len(c.inserted) == 1


def test_dry_run_does_not_insert():
    c = Fake()
    assert cal.sync(c, [IPO], now=NOW, dry_run=True).created and not c.inserted


def test_existing_by_description_key_not_duplicated():
    c = Fake([{"summary": "x", "description": "重複確認キー: " + IPO.dedupe_key()}])
    assert cal.sync(c, [IPO], now=NOW).existing and not c.inserted


def test_existing_by_private_property_not_duplicated():
    c = Fake([{"extendedProperties": {"private": {"ipoDedupeKey": IPO.dedupe_key()}}}])
    assert cal.sync(c, [IPO], now=NOW).existing and not c.inserted


def test_same_title_other_dates_is_reported_not_changed():
    c = Fake([{"summary": cal.title(IPO, Config()), "description": "old dates"}])
    assert cal.sync(c, [IPO], now=NOW).changed and not c.inserted


def test_past_is_skipped():
    c = Fake()
    assert cal.sync(c, [IPO], now=datetime(2026, 12, 1, tzinfo=JST)).past and not c.inserted


def test_selftest_always_deletes():
    c = Fake()
    assert "deleted" in cal.selftest(c)
    assert c.deleted == ["e0"]
