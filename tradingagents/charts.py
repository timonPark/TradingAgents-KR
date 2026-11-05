"""보고서 HTML 용 차트 — 사전조회 원본 데이터에서 정적 SVG 를 그린다 (#144).

- **데이터 기반·결정적**: 차트는 사전조회된 수치(OHLCV·지표·수급)만으로 그린다. LLM 이 쓴
  본문 숫자를 긁어 그리지 않는다 (틀린 차트가 사실처럼 보이는 것을 막는다).
- **실패는 빈 차트가 아니라 사유**: 데이터가 없거나 수집에 실패했으면 ``ChartGap`` 으로
  "왜 못 그렸는지"를 표시한다 (0건 위장 금지).
- 외부 리소스·스크립트 없음. 보고서 페이지의 CSP(``default-src 'none'``)에서 동작하는
  인라인 SVG 뿐이다. 색은 페이지의 CSS 변수(``--up``/``--down``/``--accent`` …)를 쓴다.
- 입력은 시장 분석가가 보존한 문자열(``final_state["market_data"]``). 이 문자열의 형식은
  우리 vendor 가 만든 것이라 결정적이며, 형식은 ``tests/test_charts.py`` 가 실제 포매터
  출력으로 고정한다.

순수 함수만 둔다 — 네트워크·파일 접근 없음.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape

# 차트 공통 크기 (viewBox). 페이지에서 폭에 맞춰 늘어난다.
_W, _H = 660, 260
_ML, _MR, _MT, _MB = 56, 16, 30, 28  # 여백: 좌(축 라벨) 우 상(범례) 하(날짜)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class Chart:
    title: str
    svg: str
    note: str = ""


@dataclass(frozen=True)
class ChartGap:
    """그리지 못한 차트와 그 사유."""

    title: str
    reason: str


# ---------------------------------------------------------------------------
# 파서 — vendor 가 만든 문자열을 수치로
# ---------------------------------------------------------------------------


def parse_ohlcv(text: str) -> list[tuple[str, float]]:
    """``Date,Open,High,Low,Close,...`` CSV → ``[(날짜, 종가)]`` (오름차순). 없으면 ``[]``."""
    rows: list[tuple[str, float]] = []
    in_table = False
    for line in (text or "").splitlines():
        if line.startswith("Date,"):
            in_table = True
            continue
        if not in_table:
            continue
        parts = line.split(",")
        if len(parts) < 5 or not _DATE_RE.match(parts[0]):
            continue
        try:
            rows.append((parts[0], float(parts[4])))
        except ValueError:
            continue
    rows.sort(key=lambda r: r[0])
    return rows


def parse_indicator(text: str, name: str) -> list[tuple[str, float]]:
    """``## {name} values from … to …`` 블록의 ``날짜: 값`` 줄 → ``[(날짜, 값)]`` (오름차순).

    ``N/A`` (영업일 아님·계산 불가) 줄은 건너뛴다.
    """
    rows: list[tuple[str, float]] = []
    in_block = False
    header = f"## {name} values"
    for line in (text or "").splitlines():
        if line.startswith("## "):
            in_block = line.startswith(header)
            continue
        if not in_block:
            continue
        date, sep, value = line.partition(": ")
        if not sep or not _DATE_RE.match(date):
            continue
        try:
            rows.append((date, float(value.replace(",", ""))))
        except ValueError:
            continue
    rows.sort(key=lambda r: r[0])
    return rows


@dataclass(frozen=True)
class InvestorFlow:
    rows: list[tuple[str, float]]  # (주체, 순매수) — unit 단위
    unit: str  # "원" | "주"
    source: str  # "KRX" | "네이버 증권"
    period: str = ""


def _number(text: str) -> float | None:
    try:
        return float(text.replace(",", "").replace("+", "").replace("*", "").strip())
    except ValueError:
        return None


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_investor_flow(text: str) -> InvestorFlow | None:
    """수급 문자열 → ``InvestorFlow``. 조회 실패·형식 불명이면 None.

    두 출처의 형식을 읽는다:
    - KRX: ``(YYYY-MM-DD ~ YYYY-MM-DD, 단위: 원, 출처: KRX)`` + 투자자 / 순매수 표
    - 네이버 증권: ``(단위: 주, 출처: 네이버 증권)`` + 일자별 표의 ``합계`` 행
    """
    text = text or ""
    if text.lstrip().startswith("[") or "단위:" not in text:
        return None
    unit_match = re.search(r"단위:\s*(원|주)", text)
    source_match = re.search(r"출처:\s*([^)\n]+)", text)
    if not unit_match or not source_match:
        return None
    unit, source = unit_match.group(1), source_match.group(1).strip()
    period_match = re.search(r"(\d{4}-\d{2}-\d{2}\s*~\s*\d{4}-\d{2}-\d{2})", text)
    period = period_match.group(1) if period_match else ""

    lines = [ln for ln in text.splitlines() if ln.strip().startswith("|")]
    if source == "네이버 증권":
        header = next((_cells(ln) for ln in lines if "외국인" in ln and "기관" in ln), None)
        total = next((_cells(ln) for ln in lines if "합계" in ln), None)
        if not header or not total or len(total) != len(header):
            return None
        rows = []
        for name, cell in zip(header[1:], total[1:], strict=False):
            value = _number(cell)
            if name in ("외국인", "기관", "개인") and value is not None:
                rows.append((name, value))
        return InvestorFlow(rows, unit, source, period) if rows else None

    rows = []
    for ln in lines:
        cells = _cells(ln)
        if len(cells) < 2 or set(cells[0]) <= set(":- "):
            continue
        value = _number(cells[1])
        if value is not None:
            rows.append((cells[0], value))
    return InvestorFlow(rows, unit, source, period) if rows else None


# ---------------------------------------------------------------------------
# SVG 도구
# ---------------------------------------------------------------------------


def _fmt_price(value: float) -> str:
    return f"{value:,.0f}"


def _nice_range(lo: float, hi: float) -> tuple[float, float]:
    if hi - lo < 1e-9:
        pad = abs(hi) * 0.05 or 1.0
        return lo - pad, hi + pad
    pad = (hi - lo) * 0.06
    return lo - pad, hi + pad


def _ticks(lo: float, hi: float, count: int = 4) -> list[float]:
    return [lo + (hi - lo) * i / count for i in range(count + 1)]


def _svg(label: str, body: str) -> str:
    return (
        f'<svg viewBox="0 0 {_W} {_H}" role="img" aria-label="{escape(label, quote=True)}">'
        f"{body}</svg>"
    )


@dataclass(frozen=True)
class Series:
    name: str
    points: list[tuple[str, float]]
    style: str  # CSS class: s1..s4 (색과 선 모양이 다르다 — 색만으로 구분하지 않는다)


def line_chart(
    title: str,
    series: list[Series],
    *,
    y_range: tuple[float, float] | None = None,
    refs: tuple[tuple[float, str], ...] = (),
    fmt=_fmt_price,
) -> Chart | None:
    """날짜별 값 선 차트. 가로축은 거래일 순서(주말·휴장일 간격 없음)."""
    series = [s for s in series if s.points]
    if not series:
        return None
    dates = sorted({d for s in series for d, _ in s.points})
    index = {d: i for i, d in enumerate(dates)}
    values = [v for s in series for _, v in s.points]
    lo, hi = y_range if y_range else _nice_range(min(values), max(values))
    span = max(len(dates) - 1, 1)
    pw, ph = _W - _ML - _MR, _H - _MT - _MB

    def x(i: int) -> float:
        return _ML + pw * i / span

    def y(v: float) -> float:
        return _MT + ph * (1 - (v - lo) / (hi - lo))

    parts = []
    for tick in _ticks(lo, hi):
        parts.append(
            f'<line class="grid" x1="{_ML}" y1="{y(tick):.1f}" x2="{_W - _MR}" y2="{y(tick):.1f}"/>'
            f'<text class="axis" x="{_ML - 6}" y="{y(tick) + 4:.1f}" text-anchor="end">'
            f"{escape(fmt(tick))}</text>"
        )
    for value, label in refs:
        parts.append(
            f'<line class="ref" x1="{_ML}" y1="{y(value):.1f}" x2="{_W - _MR}" y2="{y(value):.1f}"/>'
            f'<text class="axis" x="{_W - _MR}" y="{y(value) - 3:.1f}" text-anchor="end">'
            f"{escape(label)}</text>"
        )
    for i in sorted({0, len(dates) // 2, len(dates) - 1}):
        anchor = "start" if i == 0 else "end" if i == len(dates) - 1 else "middle"
        parts.append(
            f'<text class="axis" x="{x(i):.1f}" y="{_H - 8}" text-anchor="{anchor}">{dates[i]}</text>'
        )
    legend_x = _ML
    for s in series:
        coords = " ".join(f"{x(index[d]):.1f},{y(v):.1f}" for d, v in s.points)
        parts.append(f'<polyline class="line {s.style}" points="{coords}"/>')
        parts.append(
            f'<line class="line {s.style}" x1="{legend_x}" y1="14" x2="{legend_x + 18}" y2="14"/>'
            f'<text class="axis" x="{legend_x + 22}" y="18">{escape(s.name)}</text>'
        )
        legend_x += 30 + 7 * len(s.name) + 16
    last = ", ".join(f"{s.name} {fmt(s.points[-1][1])}" for s in series)
    label = f"{title}: {dates[0]}부터 {dates[-1]}까지, 마지막 값 {last}"
    return Chart(title, _svg(label, "".join(parts)), f"{dates[0]} ~ {dates[-1]} · 마지막 값 {last}")


def histogram_chart(title: str, points: list[tuple[str, float]], *, fmt=lambda v: f"{v:,.1f}") -> Chart | None:
    """0 을 기준으로 위(양수)/아래(음수)로 뻗는 막대 — MACD 히스토그램."""
    if not points:
        return None
    lo, hi = min(min(v for _, v in points), 0.0), max(max(v for _, v in points), 0.0)
    lo, hi = _nice_range(lo, hi)
    pw, ph = _W - _ML - _MR, _H - _MT - _MB
    slot = pw / len(points)
    bar = max(slot * 0.62, 1.5)

    def y(v: float) -> float:
        return _MT + ph * (1 - (v - lo) / (hi - lo))

    parts = []
    for tick in _ticks(lo, hi):
        parts.append(
            f'<line class="grid" x1="{_ML}" y1="{y(tick):.1f}" x2="{_W - _MR}" y2="{y(tick):.1f}"/>'
            f'<text class="axis" x="{_ML - 6}" y="{y(tick) + 4:.1f}" text-anchor="end">{escape(fmt(tick))}</text>'
        )
    parts.append(f'<line class="zero" x1="{_ML}" y1="{y(0):.1f}" x2="{_W - _MR}" y2="{y(0):.1f}"/>')
    for i, (_date, value) in enumerate(points):
        cx = _ML + slot * (i + 0.5)
        top, bottom = (y(value), y(0)) if value >= 0 else (y(0), y(value))
        cls = "up" if value >= 0 else "down"
        parts.append(
            f'<rect class="bar {cls}" x="{cx - bar / 2:.1f}" y="{top:.1f}" '
            f'width="{bar:.1f}" height="{max(bottom - top, 0.5):.1f}"/>'
        )
    for i in sorted({0, len(points) // 2, len(points) - 1}):
        anchor = "start" if i == 0 else "end" if i == len(points) - 1 else "middle"
        cx = _ML + slot * (i + 0.5)
        parts.append(
            f'<text class="axis" x="{cx:.1f}" y="{_H - 8}" text-anchor="{anchor}">{points[i][0]}</text>'
        )
    last = fmt(points[-1][1])
    label = f"{title}: {points[0][0]}부터 {points[-1][0]}까지, 마지막 값 {last}"
    return Chart(title, _svg(label, "".join(parts)), f"{points[0][0]} ~ {points[-1][0]} · 마지막 값 {last}")


# 수급 막대: 주요 주체를 먼저, 기관 세부는 아래에 묶는다.
_FLOW_MAIN = ("외국인", "기관합계", "기관", "개인", "기타법인")


def investor_flow_chart(flow: InvestorFlow) -> Chart | None:
    """투자주체별 순매수 가로 막대 (왼쪽 음수=순매도, 오른쪽 양수=순매수)."""
    if flow.unit == "원":
        scale, unit_label, digits = 1e8, "억 원", 1
    else:
        scale, unit_label, digits = 1.0, "주", 0
    rows = [(name, value / scale) for name, value in flow.rows if name != "전체"]
    main = sorted((r for r in rows if r[0] in _FLOW_MAIN), key=lambda r: _FLOW_MAIN.index(r[0]))
    detail = [r for r in rows if r[0] not in _FLOW_MAIN and r[0] not in ("기타외국인",)]
    ordered = main + detail
    if not ordered:
        return None

    def fmt(value: float) -> str:
        return f"{value:+,.{digits}f}"

    row_h = 22
    height = _MT + row_h * len(ordered) + 14
    extent = max(abs(v) for _, v in ordered) or 1.0
    label_w = 92
    x0, x1 = _ML + label_w - 40, _W - 70
    mid = (x0 + x1) / 2
    half = (x1 - x0) / 2

    parts = [f'<line class="zero" x1="{mid:.1f}" y1="{_MT - 8}" x2="{mid:.1f}" y2="{height - 8}"/>']
    parts.append(f'<text class="axis" x="{x0}" y="14">← 순매도</text>')
    parts.append(f'<text class="axis" x="{x1}" y="14" text-anchor="end">순매수 →</text>')
    for i, (name, value) in enumerate(ordered):
        cy = _MT + row_h * i + row_h / 2
        w = abs(value) / extent * half
        cls = "up" if value >= 0 else "down"
        indent = 14 if (name, value) in detail else 0
        parts.append(
            f'<text class="axis" x="{_ML - 6 + indent}" y="{cy + 4:.1f}">{escape(name)}</text>'
        )
        bx = mid if value >= 0 else mid - w
        parts.append(
            f'<rect class="bar {cls}" x="{bx:.1f}" y="{cy - 7:.1f}" width="{max(w, 0.5):.1f}" height="14"/>'
        )
        tx = mid + w + 4 if value >= 0 else mid - w - 4
        anchor = "start" if value >= 0 else "end"
        parts.append(
            f'<text class="axis" x="{tx:.1f}" y="{cy + 4:.1f}" text-anchor="{anchor}">{fmt(value)}</text>'
        )
    summary = ", ".join(f"{n} {fmt(v)}" for n, v in main) or ", ".join(f"{n} {fmt(v)}" for n, v in ordered[:3])
    title = f"투자주체별 순매수 ({unit_label})"
    label = f"{title}: {summary}"
    svg = (
        f'<svg viewBox="0 0 {_W} {height}" role="img" aria-label="{escape(label, quote=True)}">'
        f'{"".join(parts)}</svg>'
    )
    note = f"{flow.period + ' · ' if flow.period else ''}출처: {flow.source} · 단위: {unit_label}"
    if flow.source != "KRX":
        note += " · 기관 세부 구분 없음"
    return Chart(title, svg, note)


# ---------------------------------------------------------------------------
# 시장 분석가 차트 묶음
# ---------------------------------------------------------------------------

_FAILED_MARK = ("[prefetch failed", "[KRX 수급 조회 실패")


def _sma(rows: list[tuple[str, float]], window: int) -> list[tuple[str, float]]:
    out = []
    for i in range(window - 1, len(rows)):
        out.append((rows[i][0], sum(v for _, v in rows[i - window + 1 : i + 1]) / window))
    return out


def _reason(text: str, default: str) -> str:
    text = (text or "").strip()
    if not text:
        return default
    if text.startswith(_FAILED_MARK):
        return text[:160]
    return default


def build_market_charts(market_data: dict[str, str] | None) -> list[Chart | ChartGap]:
    """시장 분석가 사전조회 데이터(``ohlcv``/``indicators``/``investor_flow``)로 차트를 만든다.

    ``market_data`` 가 없으면 (예전 run) 빈 리스트 — 차트 영역을 만들지 않는다.
    """
    if not market_data:
        return []
    out: list[Chart | ChartGap] = []

    ohlcv_text = market_data.get("ohlcv", "")
    closes = parse_ohlcv(ohlcv_text)
    indicators = market_data.get("indicators", "")

    price_title = "가격과 이동평균"
    chart = None
    if closes:
        chart = line_chart(
            price_title,
            [
                Series("종가", closes, "s1"),
                Series("50일 이동평균", _sma(closes, 50), "s2"),
                Series("200일 이동평균", _sma(closes, 200), "s3"),
            ],
        )
    out.append(chart or ChartGap(price_title, _reason(ohlcv_text, "가격 데이터가 없어 그리지 못했습니다.")))

    boll_title = "볼린저 밴드 (최근 30일)"
    boll_mid = parse_indicator(indicators, "boll")
    window = {d for d, _ in boll_mid}  # 지표 창(달력 30일)과 같은 날짜의 종가만
    close_30 = [row for row in closes if row[0] in window]
    chart = line_chart(
        boll_title,
        [
            Series("상단", parse_indicator(indicators, "boll_ub"), "s3"),
            Series("종가", close_30, "s1"),
            Series("중심", boll_mid, "s2"),
            Series("하단", parse_indicator(indicators, "boll_lb"), "s4"),
        ],
    )
    out.append(chart or ChartGap(boll_title, _reason(indicators, "볼린저 밴드 지표 데이터가 없어 그리지 못했습니다.")))

    macd_title = "MACD 히스토그램"
    chart = histogram_chart(macd_title, parse_indicator(indicators, "macdh"))
    out.append(chart or ChartGap(macd_title, _reason(indicators, "MACD 지표 데이터가 없어 그리지 못했습니다.")))

    rsi_title = "RSI (최근 30일)"
    chart = line_chart(
        rsi_title,
        [Series("RSI", parse_indicator(indicators, "rsi"), "s1")],
        y_range=(0.0, 100.0),
        refs=((30.0, "과매도 30"), (70.0, "과매수 70")),
        fmt=lambda v: f"{v:.0f}",
    )
    out.append(chart or ChartGap(rsi_title, _reason(indicators, "RSI 지표 데이터가 없어 그리지 못했습니다.")))

    flow_text = market_data.get("investor_flow", "")
    flow = parse_investor_flow(flow_text)
    chart = investor_flow_chart(flow) if flow else None
    out.append(chart or ChartGap("투자주체별 순매수", _reason(flow_text, "수급 데이터가 없어 그리지 못했습니다.")))
    return out


def render_charts_html(items: list[Chart | ChartGap]) -> str:
    """차트 묶음을 보고서 HTML 조각으로. 비어 있으면 빈 문자열."""
    if not items:
        return ""
    figures = []
    for item in items:
        if isinstance(item, Chart):
            caption = f'<figcaption>{escape(item.note)}</figcaption>' if item.note else ""
            figures.append(
                f'<figure class="viz"><div class="viz-title">{escape(item.title)}</div>'
                f'<div class="scroll">{item.svg}</div>{caption}</figure>'
            )
        else:
            figures.append(
                f'<figure class="viz viz-gap"><div class="viz-title">{escape(item.title)}</div>'
                f'<p>차트 없음 — {escape(item.reason)}</p></figure>'
            )
    return '<div class="viz-group"><h4>차트</h4>' + "".join(figures) + "</div>"
