from datetime import date
from pathlib import Path

import pytest

from ipo_sync.sbi import ParseError, parse

FIX = Path(__file__).parent / "fixture_sbi.html"


def test_parse_ipo_only_and_dates():
    ipos = parse(FIX.read_text(encoding="utf-8"), today=date(2026, 11, 10))
    assert [i.name for i in ipos] == ["Ｂｅｙｏｎｔ", "ＫＤＸ　Ｋｏｌｅｔ投資法人"]  # POは除外、（株）は除く
    b = ipos[0]
    assert (b.code, b.market) == ("674A", "東証グロース")
    assert b.bb_start == "2026-11-26T00:00:00+09:00"
    assert b.bb_end == "2026-12-02T11:00:00+09:00"
    assert (b.price_decision_date, b.lottery_date, b.listing_date) == ("2026-11-25", "2026-12-03", "2026-12-11")
    assert b.dedupe_key() == "Ｂｅｙｏｎｔ_ブックビル期間_2026-11-26T00:00:00+09:00_2026-12-02T11:00:00+09:00"


def test_year_rollover():
    k = parse(FIX.read_text(encoding="utf-8"), today=date(2026, 11, 10))[1]
    assert k.bb_start == "2026-12-28T00:00:00+09:00"
    assert k.bb_end == "2027-01-06T11:00:00+09:00"
    assert (k.lottery_date, k.listing_date) == ("2027-01-07", "2027-01-20")


def test_zero_ipos_is_an_error():
    with pytest.raises(ParseError):
        parse("<html><h3>IPO (新規上場株)</h3><h3>PO</h3></html>", today=date(2026, 11, 10))
    with pytest.raises(ParseError):
        parse("<html></html>", today=date(2026, 11, 10))


def test_issuer_without_bb_period_is_skipped():
    html = FIX.read_text(encoding="utf-8").replace("12/28 0:00～1/6 11:00", "-")
    skipped: list[str] = []
    ipos = parse(html, today=date(2026, 11, 10), skipped=skipped)
    assert [i.name for i in ipos] == ["Ｂｅｙｏｎｔ"]
    assert skipped == ["ＫＤＸ　Ｋｏｌｅｔ投資法人"]
