import pytest

from ipo_sync.config import Config, reminder_minutes


def test_prev_day_reminder():
    assert reminder_minutes("prev@19:00,30", "2026-11-24T00:00:00+09:00") == [300, 30]
    assert reminder_minutes("prev@19:00", "2026-11-12T13:00:00+09:00") == [300 + 780]
    assert reminder_minutes("prev@09:30", "2026-11-12T00:00:00+09:00") == [870]
    assert reminder_minutes("none", "2026-11-12T00:00:00+09:00") == []


def test_bad_reminder_rejected():
    with pytest.raises(ValueError):
        reminder_minutes("tomorrow", "2026-11-12T00:00:00+09:00")


def test_env_defaults_and_overrides(monkeypatch):
    for k in ("IPO_TITLE_PREFIX", "IPO_COLOR_ID", "IPO_REMINDERS", "IPO_SHOW_AS"):
        monkeypatch.setenv(k, "")
    assert Config.from_env() == Config()
    monkeypatch.setenv("IPO_COLOR_ID", "11")
    monkeypatch.setenv("IPO_SHOW_AS", "BUSY")
    c = Config.from_env()
    assert (c.color_id, c.show_as) == ("11", "busy")


def test_bad_color_rejected(monkeypatch):
    monkeypatch.setenv("IPO_COLOR_ID", "12")
    with pytest.raises(ValueError):
        Config.from_env()
