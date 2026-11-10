"""Fetch the public SBI Securities IPO list (static HTML, Shift_JIS) and extract book-building periods."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

JST = ZoneInfo("Asia/Tokyo")
SBI_URL = (
    "https://www.sbisec.co.jp/ETGate/?OutSide=on&_ControlID=WPLETmgR001Control"
    "&_DataStoreID=DSWPLETmgR001Control&burl=search_domestic&cat1=domestic&cat2=ipo"
    "&dir=ipo%2F&file=stock_info_ipo.html&getFlg=on"
)


class ParseError(Exception):
    """Raised when the page does not look as expected. Zero results is treated as an error."""


@dataclass
class Ipo:
    name: str  # company name as shown on the page, without "（株）"
    code: str
    market: str
    bb_start: str  # book-building start, ISO 8601 with +09:00
    bb_end: str
    price_decision_date: str | None  # 仮条件決定日 (YYYY-MM-DD)
    lottery_date: str | None  # 発行価格決定日（抽選日）
    listing_date: str | None

    def dedupe_key(self) -> str:
        return f"{self.name}_ブックビル期間_{self.bb_start}_{self.bb_end}"

    def asdict(self) -> dict:
        return asdict(self)


def fetch_html(url: str = SBI_URL, timeout: int = 30) -> str:
    last: Exception | None = None
    for _ in range(3):
        try:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": "ipo-calendar-sync"})
            r.raise_for_status()
            return r.content.decode("cp932", errors="replace")
        except requests.RequestException as e:  # noqa: PERF203
            last = e
    raise ParseError(f"could not fetch the SBI page: {last}")


def _clean_name(s: str) -> str:
    return re.sub(r"[（(]株[）)]", "", s.strip()).strip()  # drop "（株）", keep full-width text as is


def _md(s: str) -> tuple[int, int, int, int]:
    """'11/26 0:00' -> (11, 26, 0, 0). Time defaults to 0:00."""
    m = re.search(r"(\d{1,2})/(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?", s)
    if not m:
        raise ParseError(f"cannot read date: {s!r}")
    return int(m[1]), int(m[2]), int(m[3] or 0), int(m[4] or 0)


def _year_for(month: int, day: int, today: date) -> int:
    """The page has no year. A date more than ~6 months in the past is taken as next year."""
    y = today.year
    if date(y, month, day) < today - timedelta(days=180):
        y += 1
    return y


def _iso(y: int, mo: int, d: int, h: int, mi: int) -> str:
    return datetime(y, mo, d, h, mi, tzinfo=JST).isoformat()


def parse(html: str, today: date | None = None, skipped: list[str] | None = None) -> list[Ipo]:
    """Parse the "IPO (新規上場株)" section only (the "PO" section is ignored).

    Issuers whose book-building period is not set yet ("-") are appended to `skipped`.
    """
    today = today or datetime.now(JST).date()
    soup = BeautifulSoup(html, "lxml")
    start = next((h for h in soup.find_all("h3") if h.get_text(strip=True).startswith("IPO")), None)
    if start is None:
        raise ParseError('heading "IPO (新規上場株)" not found')
    out: list[Ipo] = []
    for el in start.next_elements:
        name = getattr(el, "name", None)
        if name == "h3" and el is not start:
            break  # reached the next section (PO)
        if name != "div" or "seeds-mb-x-6" not in (el.get("class") or []) or el.find("h4") is None:
            continue
        ipo = _parse_box(el, today)
        if ipo is None:
            if skipped is not None:
                skipped.append(_clean_name(el.find("h4").get_text(strip=True)))
            continue
        out.append(ipo)
    if not out:
        raise ParseError("0 IPOs found (the page layout may have changed)")
    return out


def _cells(box) -> dict[str, str]:
    cells: dict[str, str] = {}
    for li in box.select("li.seeds-table-row"):
        head = None
        for div in li.find_all("div", recursive=False):
            cls = div.get("class") or []
            text = re.sub(r"\s+", " ", div.get_text(" ", strip=True))
            if "seeds-table-head" in cls:
                head = text
            elif "seeds-table-item" in cls and head:
                cells[head] = text
                head = None
    return cells


def _parse_box(box, today: date) -> Ipo | None:
    name = _clean_name(box.find("h4").get_text(strip=True))
    sub = box.select_one("p.seeds-text-sub")
    code, _, market = re.sub(r"\s+", " ", sub.get_text(" ", strip=True) if sub else "").partition(" ")
    cells = _cells(box)
    bb = cells.get("ブックビル期間")
    if bb is not None and not re.search(r"\d", bb):
        return None  # period not decided yet
    if not bb or "～" not in bb:
        raise ParseError(f"{name}: cannot read book-building period: {bb!r}")
    left, right = bb.split("～", 1)
    sm, sd, sh, smi = _md(left)
    em, ed, eh, emi = _md(right)
    sy = _year_for(sm, sd, today)
    ey = sy + 1 if (em, ed) < (sm, sd) else sy
    bb_start_date = date(sy, sm, sd)

    def near(mo: int, d: int) -> str:
        """Pick the year closest to the book-building start (handles year boundaries)."""
        cands = [date(y, mo, d) for y in (sy - 1, sy, sy + 1)]
        return min(cands, key=lambda c: abs((c - bb_start_date).days)).isoformat()

    def one(label: str) -> str | None:
        v = cells.get(label)
        if not v or not re.search(r"\d{1,2}/\d{1,2}", v):
            return None
        mo, d, *_ = _md(v)
        return near(mo, d)

    notes = box.select_one("div.selling-notes")
    lottery = None
    if notes:
        m = re.search(r"発行価格決定日（抽選日）\s*(\d{1,2})/(\d{1,2})", notes.get_text(" ", strip=True))
        if m:
            lottery = near(int(m[1]), int(m[2]))
    return Ipo(
        name=name,
        code=code,
        market=market,
        bb_start=_iso(sy, sm, sd, sh, smi),
        bb_end=_iso(ey, em, ed, eh, emi),
        price_decision_date=one("仮条件決定日"),
        lottery_date=lottery,
        listing_date=one("上場日"),
    )
