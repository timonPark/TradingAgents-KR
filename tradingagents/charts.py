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

import json
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


def _svg(label: str, body: str, height: int = _H) -> str:
    return (
        f'<svg viewBox="0 0 {_W} {height}" role="img" aria-label="{escape(label, quote=True)}">'
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


def render_charts_html(items: list[Chart | ChartGap], heading: str | None = "차트") -> str:
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
    title = f"<h4>{escape(heading)}</h4>" if heading else ""
    return f'<div class="viz-group">{title}' + "".join(figures) + "</div>"


# ---------------------------------------------------------------------------
# 한국 거시 지표 (한국은행 ECOS) — 뉴스 분석가 섹션
# ---------------------------------------------------------------------------

_MACRO_ORDER = (
    ("treasury_10y", "국고채 10년 금리"),
    ("usd_krw", "원/달러 환율"),
    ("base_rate", "한국은행 기준금리"),
    ("cpi", "소비자물가지수"),
    ("unemployment_rate", "실업률"),
    ("consumer_sentiment", "소비자심리지수"),
)


def _macro_gap_reason(text: str) -> str:
    """수집 실패 문구(``[prefetch failed …]``/``DATA_UNAVAILABLE …``)는 그대로, 아니면 기본 사유."""
    first = (text or "").strip().splitlines()[0][:160] if (text or "").strip() else ""
    if first.startswith(("[prefetch failed", "DATA_UNAVAILABLE")):
        return first
    return "관측 데이터가 없어 그리지 못했습니다."


def _ecos_date(raw: str) -> str | None:
    if re.fullmatch(r"\d{8}", raw):
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    if re.fullmatch(r"\d{6}", raw):
        return f"{raw[:4]}-{raw[4:]}"
    if re.fullmatch(r"\d{4}Q[1-4]", raw):
        return raw
    return None


def parse_ecos_section(text: str) -> tuple[str, list[tuple[str, float]]] | None:
    """ECOS vendor 의 지표 섹션 → ``(단위, [(기간, 값)])`` (기간 오름차순). 관측값이 없으면 None.

    섹션은 ``- **단위**: 연%`` 줄과 ``| 기간 | 값 |`` 표로 이루어진다 (``ecos.py`` 포매터).
    """
    text = text or ""
    unit_match = re.search(r"^- \*\*단위\*\*:\s*(.+)$", text, re.MULTILINE)
    unit = unit_match.group(1).strip() if unit_match else ""
    rows: list[tuple[str, float]] = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = _cells(line)
        if len(cells) < 2:
            continue
        period = _ecos_date(cells[0])
        value = _number(cells[1])
        if period and value is not None:
            rows.append((period, value))
    if not rows:
        return None
    rows.sort(key=lambda r: r[0])
    return unit, rows


def _value_fmt(values: list[float]):
    span = max(values) - min(values)
    digits = 0 if span >= 20 else 1 if span >= 2 else 2 if span >= 0.2 else 3
    return lambda v: f"{v:,.{digits}f}"


def build_macro_charts(macro_data: dict[str, str] | None) -> list[Chart | ChartGap]:
    """뉴스 분석가가 보존한 ECOS 지표 섹션(``macro_data``)으로 지표별 선 차트를 만든다.

    ``macro_data`` 가 없으면 (예전 run) 빈 리스트. 관측값이 없거나 수집에 실패한 지표는
    ``ChartGap`` 으로 사유를 남긴다.
    """
    if not macro_data:
        return []
    out: list[Chart | ChartGap] = []
    for key, name in _MACRO_ORDER:
        text = macro_data.get(key)
        if text is None:
            continue
        parsed = parse_ecos_section(text)
        if parsed is None:
            out.append(ChartGap(name, _macro_gap_reason(text)))
            continue
        unit, rows = parsed
        title = f"{name} ({unit})" if unit and unit != "—" else name
        values = [v for _, v in rows]
        chart = None
        if len(rows) >= 2:
            chart = line_chart(title, [Series(name, rows, "s1")], fmt=_value_fmt(values))
        out.append(chart or ChartGap(title, "관측값이 1개뿐이라 추이를 그리지 못했습니다."))
    return out


# ---------------------------------------------------------------------------
# 한눈에 보기 — 에이전트별 판정 흐름
# ---------------------------------------------------------------------------

# 방향: up(강세 쪽) / level(중립) / down(약세 쪽) / none(판독 불가)
_RATING_DIRECTION = {"Buy": "up", "Overweight": "up", "Hold": "level", "Underweight": "down", "Sell": "down"}
_BAND_DIRECTION = {
    "Bullish": "up", "Mildly Bullish": "up", "Neutral": "level", "Mixed": "level",
    "Mildly Bearish": "down", "Bearish": "down",
}
_MARK = {"up": "▲", "level": "■", "down": "▼", "none": "?"}


@dataclass(frozen=True)
class VerdictNode:
    role: str  # 에이전트 이름
    verdict: str  # 화면 표기 (한국어)
    direction: str  # up | level | down | none


def _recommendation(text: str) -> str | None:
    """리서치 매니저 ``**추천**: …`` 줄의 등급(내부 값). 없으면 None."""
    from tradingagents.agents.rating import canonical_rating

    match = re.search(
        r"^\W*\*\*(?:추천|Recommendation)\*\*\s*:\s*\**\s*(비중\s*확대|비중\s*축소|\w+)",
        text or "", re.MULTILINE,
    )
    return canonical_rating(match.group(1)) if match else None


def _sentiment_band(text: str) -> str | None:
    """감성 분석가 머리글의 센티먼트(내부 값). 한국어·영어 머리글 모두 읽는다."""
    from tradingagents.agents.schemas import SENTIMENT_BAND_KO

    reverse = {ko: en for en, ko in SENTIMENT_BAND_KO.items()}
    match = re.search(r"\*\*(?:전체 센티먼트|Overall Sentiment):\*\*\s*\*\*([^*]+)\*\*", text or "")
    if not match:
        return None
    label = match.group(1).strip()
    return reverse.get(label) or (label if label in _BAND_DIRECTION else None)


def build_verdict_flow(final_state: dict) -> list[VerdictNode]:
    """구조화된 판정 줄에서 에이전트별 판정 흐름을 만든다. 2개 미만이면 빈 리스트.

    감성 분석가 → 리서치 매니저 → 트레이더 → 포트폴리오 매니저. 본문에서 의견을 추정하지
    않고, 포맷이 보장하는 판정 줄(``전체 센티먼트``/``추천``/``최종 거래 제안``/``등급``)만
    읽는다. 읽지 못한 단계는 "판독 불가"로 남긴다 (건너뛰어 흐름을 꾸미지 않는다).
    """
    from tradingagents.agents.rating import (
        RATING_REVIEW,
        display_rating,
        extract_rating,
        run_rating,
    )
    from tradingagents.agents.schemas import SENTIMENT_BAND_KO

    def node_from_rating(role: str, rating: str | None) -> VerdictNode:
        if not rating or rating == RATING_REVIEW:
            return VerdictNode(role, "판독 불가", "none")
        return VerdictNode(role, display_rating(rating), _RATING_DIRECTION.get(rating, "none"))

    nodes: list[VerdictNode] = []
    if final_state.get("sentiment_report"):
        band = _sentiment_band(final_state["sentiment_report"])
        nodes.append(VerdictNode("감성 분석가", SENTIMENT_BAND_KO.get(band, "판독 불가"),
                                 _BAND_DIRECTION.get(band, "none")) if band
                     else VerdictNode("감성 분석가", "판독 불가", "none"))
    if final_state.get("investment_plan"):
        nodes.append(node_from_rating("리서치 매니저", _recommendation(final_state["investment_plan"])))
    if final_state.get("trader_investment_plan"):
        nodes.append(node_from_rating("트레이더", extract_rating(final_state["trader_investment_plan"])))
    if final_state.get("final_trade_decision"):
        nodes.append(node_from_rating("포트폴리오 매니저", run_rating(final_state)))
    return nodes if len(nodes) >= 2 else []


def verdict_flow_chart(nodes: list[VerdictNode]) -> Chart | None:
    """판정 흐름: 단계별 상자를 화살표로 잇는다. 방향은 색과 기호(▲ ■ ▼)로 함께 표시."""
    if not nodes:
        return None
    gap, box_w, box_h = 28, 132, 78
    width = len(nodes) * box_w + (len(nodes) - 1) * gap
    scale_w = max(width, 1)
    parts = []
    for i, node in enumerate(nodes):
        x = i * (box_w + gap)
        parts.append(
            f'<g class="flow {node.direction}">'
            f'<rect class="node" x="{x}" y="14" width="{box_w}" height="{box_h}" rx="6"/>'
            f'<text class="role" x="{x + box_w / 2}" y="36" text-anchor="middle">{escape(node.role)}</text>'
            f'<text class="verdict" x="{x + box_w / 2}" y="66" text-anchor="middle">'
            f'{_MARK[node.direction]} {escape(node.verdict)}</text></g>'
        )
        if i < len(nodes) - 1:
            ax = x + box_w
            parts.append(
                f'<path class="arrow" d="M{ax + 4} {14 + box_h / 2} H{ax + gap - 4}"/>'
                f'<path class="arrow" d="M{ax + gap - 10} {14 + box_h / 2 - 5} L{ax + gap - 4} '
                f'{14 + box_h / 2} L{ax + gap - 10} {14 + box_h / 2 + 5}"/>'
            )
    summary = " → ".join(f"{n.role} {n.verdict}" for n in nodes)
    height = 14 + box_h + 14
    svg = (
        f'<svg viewBox="0 0 {scale_w} {height}" role="img" '
        f'aria-label="{escape("에이전트별 판정 흐름: " + summary, quote=True)}">{"".join(parts)}</svg>'
    )
    return Chart("에이전트별 판정 흐름", svg, summary)


# ---------------------------------------------------------------------------
# 가격 레벨 — 트레이더·포트폴리오 매니저가 제시한 가격
# ---------------------------------------------------------------------------

_LEVEL_LABELS = {
    "entry": (("진입가", "Entry Price"), "진입가"),
    "stop": (("손절가", "Stop Loss"), "손절가"),
    "target": (("목표가", "Price Target"), "목표가"),
}
_NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


@dataclass(frozen=True)
class PriceLevel:
    kind: str  # current | entry | stop | target
    label: str
    value: float


def _labelled_price(text: str, labels: tuple[str, ...]) -> float | None:
    """``**진입가**: 52000.0`` 줄의 숫자. "제공되지 않음" 등 숫자가 없으면 None."""
    pattern = r"^\W*\*\*(?:" + "|".join(re.escape(label) for label in labels) + r")\*\*\s*:\s*([^\n]+)"
    match = re.search(pattern, text or "", re.MULTILINE)
    if not match:
        return None
    number = _NUMBER_RE.search(match.group(1))
    return _number(number.group(0)) if number else None


def parse_price_levels(final_state: dict) -> list[PriceLevel]:
    """상태에서 현재가·진입가·손절가·목표가를 읽는다.

    진입가·손절가는 트레이더, 목표가는 포트폴리오 매니저의 구조화 줄에서, 현재가는 사전조회
    OHLCV 의 마지막 종가에서 읽는다. 에이전트 본문의 가격은 읽지 않는다.
    """
    levels: list[PriceLevel] = []
    closes = parse_ohlcv((final_state.get("market_data") or {}).get("ohlcv", ""))
    if closes:
        levels.append(PriceLevel("current", "현재가", closes[-1][1]))
    trader = final_state.get("trader_investment_plan", "")
    decision = final_state.get("final_trade_decision", "")
    for kind, source in (("entry", trader), ("stop", trader), ("target", decision)):
        labels, shown = _LEVEL_LABELS[kind]
        value = _labelled_price(source, labels)
        if value is not None:
            levels.append(PriceLevel(kind, shown, value))
    return levels


def price_levels_chart(levels: list[PriceLevel]) -> Chart | None:
    """가격 사다리: 현재가 대비 진입가·손절가·목표가의 위치와 차이(%).

    선 모양(실선·점선·긴 점선)과 글자로도 구분해 색만으로 구분하지 않는다.
    """
    if len(levels) < 2:
        return None
    current = next((lv.value for lv in levels if lv.kind == "current"), None)
    lo, hi = _nice_range(min(lv.value for lv in levels), max(lv.value for lv in levels))
    top, bottom = 24, 276
    x0, x1 = 24, _W - 24

    def y(value: float) -> float:
        return top + (bottom - top) * (1 - (value - lo) / (hi - lo))

    ordered = sorted(levels, key=lambda lv: y(lv.value))
    label_y: list[float] = []
    for lv in ordered:  # 글자가 겹치지 않게 위에서부터 최소 간격을 둔다
        pos = y(lv.value)
        if label_y and pos < label_y[-1] + 18:
            pos = label_y[-1] + 18
        label_y.append(pos)
    overflow = label_y[-1] - (bottom + 8)
    if overflow > 0:
        label_y = [pos - overflow for pos in label_y]
        for i in range(len(label_y) - 2, -1, -1):
            label_y[i] = min(label_y[i], label_y[i + 1] - 18)

    parts = []
    for lv, ly in zip(ordered, label_y, strict=True):
        py = y(lv.value)
        diff = ""
        if current and lv.kind != "current":
            diff = f" ({(lv.value / current - 1) * 100:+.1f}%)"
        parts.append(
            f'<g class="lvl {lv.kind}"><line x1="{x0}" y1="{py:.1f}" x2="{x1 - 230}" y2="{py:.1f}"/>'
            f'<text x="{x1}" y="{ly + 4:.1f}" text-anchor="end">'
            f"{escape(lv.label)} {escape(_fmt_price(lv.value))}원{escape(diff)}</text></g>"
        )
    summary = ", ".join(f"{lv.label} {_fmt_price(lv.value)}원" for lv in sorted(levels, key=lambda lv: -lv.value))
    svg = _svg(f"가격 레벨: {summary}", "".join(parts), 300)
    note = "현재가는 사전조회 마지막 종가, 진입가·손절가는 트레이더, 목표가는 포트폴리오 매니저가 제시한 값"
    return Chart("가격 레벨 (거래 계획)", svg, note)


def build_price_levels(final_state: dict) -> Chart | ChartGap | None:
    """거래 계획이 있는 run 의 가격 레벨 차트.

    그릴 수 있으면 차트. 트레이더 단계가 있었는데 가격을 하나도 제시하지 않았으면 빈 차트
    대신 사유. 트레이더 단계가 없고 그릴 가격도 없으면 None (영역을 만들지 않는다).
    """
    chart = price_levels_chart(parse_price_levels(final_state))
    if chart:
        return chart
    if final_state.get("trader_investment_plan"):
        return ChartGap("가격 레벨 (거래 계획)", "트레이더가 진입가·손절가를 제시하지 않았고 목표가도 없어 그리지 못했습니다.")
    return None


# ---------------------------------------------------------------------------
# 재무 차트 — DART 표준 계정 ID 로 뽑은 핵심 계정 (#149)
# ---------------------------------------------------------------------------


def parse_financial_accounts(text: str) -> dict | None:
    """``dart.get_financial_accounts`` 의 JSON 문자열 → dict. 실패 문구·형식 불명이면 None."""
    try:
        data = json.loads(text or "")
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("accounts"), dict):
        return None
    return data


def _won_scale(values: list[float]) -> tuple[float, str, int]:
    """금액 크기에 맞는 단위: (나눌 값, 라벨, 소수 자릿수)."""
    peak = max((abs(v) for v in values), default=0.0)
    if peak >= 1e12:
        return 1e12, "조 원", 2
    return 1e8, "억 원", 1 if peak < 1e11 else 0


def _account(accounts: dict, key: str) -> float | None:
    item = accounts.get(key)
    if isinstance(item, dict) and isinstance(item.get("value"), int | float):
        return float(item["value"])
    return None


_STANDALONE_BARS = {"asset": "up", "debt": "down"}   # kind → 막대 색 구분


def waterfall_chart(
    title: str, steps: list[tuple[str, float, str]], *, note: str, scale: tuple[float, str, int]
) -> Chart | None:
    """폭포 차트. ``steps`` = ``[(이름, 값, "total"|"delta"|"asset"|"debt")]`` (값은 원 단위).

    ``total`` 은 0 에서 값까지, ``delta`` 는 직전 수준에서 증감만큼 움직인다. 증가·감소는 색과
    부호(+/-)로 함께 표시하고, 막대 사이를 직전 수준선으로 잇는다. ``asset``·``debt`` 는 수준을
    잇지 않고 0 에서 값까지 서 있는 독립 막대다 (유동성 차트: 자산은 ``up`` 색, 부채는 ``down`` 색).
    """
    if not steps:
        return None
    divisor, unit_label, digits = scale
    spans: list[tuple[float, float, str, float]] = []   # (시작, 끝, 구분, 값) — 억/조 단위
    level = 0.0
    for _name, raw, kind in steps:
        value = raw / divisor
        if kind == "total":
            spans.append((0.0, value, "total", value))
            level = value
        elif kind in _STANDALONE_BARS:
            spans.append((0.0, value, _STANDALONE_BARS[kind], value))
        else:
            spans.append((level, level + value, "up" if value >= 0 else "down", value))
            level += value
    floor = min(0.0, *(min(a, b) for a, b, _, _ in spans))
    lo, hi = _nice_range(floor, max(0.0, *(max(a, b) for a, b, _, _ in spans)))
    if floor >= 0.0:      # 음수가 없으면 0 아래로 축을 늘리지 않는다
        lo = 0.0
    height, top, bottom = 300, 30, 52
    pw = _W - _ML - _MR
    ph = height - top - bottom
    slot = pw / len(steps)
    bar = min(slot * 0.56, 64.0)

    def y(v: float) -> float:
        return top + ph * (1 - (v - lo) / (hi - lo))

    def fmt(v: float) -> str:
        return f"{v:,.{digits}f}"

    parts = []
    for tick in _ticks(lo, hi):
        parts.append(
            f'<line class="grid" x1="{_ML}" y1="{y(tick):.1f}" x2="{_W - _MR}" y2="{y(tick):.1f}"/>'
            f'<text class="axis" x="{_ML - 6}" y="{y(tick) + 4:.1f}" text-anchor="end">{escape(fmt(tick))}</text>'
        )
    parts.append(f'<line class="zero" x1="{_ML}" y1="{y(0):.1f}" x2="{_W - _MR}" y2="{y(0):.1f}"/>')
    for i, ((name, _raw, kind), (start, end, cls, value)) in enumerate(zip(steps, spans, strict=True)):
        cx = _ML + slot * (i + 0.5)
        top_v, bottom_v = max(start, end), min(start, end)
        parts.append(
            f'<rect class="bar {cls}" x="{cx - bar / 2:.1f}" y="{y(top_v):.1f}" width="{bar:.1f}" '
            f'height="{max(y(bottom_v) - y(top_v), 1.0):.1f}"/>'
        )
        above = value >= 0
        label_y = y(top_v) - 5 if above else y(bottom_v) + 13
        shown = f"{value:+,.{digits}f}" if kind == "delta" else fmt(value)
        parts.append(f'<text class="axis val" x="{cx:.1f}" y="{label_y:.1f}" text-anchor="middle">{escape(shown)}</text>')
        parts.append(f'<text class="axis" x="{cx:.1f}" y="{height - 30}" text-anchor="middle">{escape(name)}</text>')
        if i < len(steps) - 1 and kind not in _STANDALONE_BARS and steps[i + 1][2] not in _STANDALONE_BARS:
            nxt_x = _ML + slot * (i + 1.5)
            parts.append(
                f'<line class="link" x1="{cx + bar / 2:.1f}" y1="{y(end):.1f}" '
                f'x2="{nxt_x - bar / 2:.1f}" y2="{y(end):.1f}"/>'
            )
    summary = ", ".join(f"{n} {fmt(sp[3])}" for (n, _r, _k), sp in zip(steps, spans, strict=True))
    svg = _svg(f"{title}: {summary} ({unit_label})", "".join(parts), height)
    return Chart(title, svg, f"{note} · 단위: {unit_label}")


def _financial_note(data: dict) -> str:
    return f"{data.get('year', '')}년 {data.get('period', '')} · {data.get('basis', '')} 재무제표 · 출처: DART"


def income_waterfall(data: dict) -> Chart | ChartGap:
    title = "손익 폭포"
    accounts = data["accounts"]
    revenue, operating, net = (_account(accounts, k) for k in ("revenue", "operating_income", "net_income"))
    missing = [name for name, v in (("매출액", revenue), ("영업이익", operating), ("당기순이익", net)) if v is None]
    if missing:
        return ChartGap(title, f"{', '.join(missing)} 계정을 DART 표준 계정 ID 로 찾지 못했습니다.")
    gross = _account(accounts, "gross_profit")
    steps: list[tuple[str, float, str]] = [("매출액", revenue, "total")]
    if gross is not None:
        steps += [("매출원가", gross - revenue, "delta"), ("매출총이익", gross, "total"),
                  ("판관비 등", operating - gross, "delta")]
    else:
        steps.append(("영업비용 등", operating - revenue, "delta"))
    steps += [("영업이익", operating, "total"), ("영업외·법인세 등", net - operating, "delta"),
              ("당기순이익", net, "total")]
    scale = _won_scale([v for _, v, _ in steps])
    chart = waterfall_chart(title, steps, note=_financial_note(data), scale=scale)
    return chart or ChartGap(title, "그릴 계정이 없습니다.")


def cash_bridge(data: dict) -> Chart | ChartGap:
    title = "현금 흐름 브리지"
    accounts = data["accounts"]
    begin, end, cfo, cfi, cff = (_account(accounts, k) for k in
                                 ("cash_begin", "cash_end", "cfo", "cfi", "cff"))
    names = (("기초 현금", begin), ("기말 현금", end), ("영업활동 현금흐름", cfo),
             ("투자활동 현금흐름", cfi), ("재무활동 현금흐름", cff))
    missing = [name for name, v in names if v is None]
    if missing:
        return ChartGap(title, f"{', '.join(missing)} 계정을 DART 표준 계정 ID 로 찾지 못했습니다.")
    other = end - begin - cfo - cfi - cff     # 환율 변동 등. 값이 맞지 않으면 숨기지 않고 보여준다
    steps: list[tuple[str, float, str]] = [("기초 현금", begin, "total"), ("영업활동", cfo, "delta"),
                                           ("투자활동", cfi, "delta"), ("재무활동", cff, "delta")]
    if abs(other) >= 1.0:
        steps.append(("환율·기타", other, "delta"))
    steps.append(("기말 현금", end, "total"))
    scale = _won_scale([v for _, v, _ in steps])
    chart = waterfall_chart(title, steps, note=_financial_note(data), scale=scale)
    return chart or ChartGap(title, "그릴 계정이 없습니다.")


_LIQUIDITY_ASSETS = (("cash", "현금및현금성자산"), ("short_term_deposits", "단기금융상품"))
_LIQUIDITY_DEBTS = (("short_borrowings", "단기차입금"), ("current_long_term_debt", "유동성장기부채"),
                    ("current_convertible_bonds", "유동성전환사채"))


def liquidity_chart(data: dict) -> Chart | ChartGap:
    """현금성 자산(자산 색) vs 단기 차입·전환사채(부채 색) — 재무상태표 표준 계정 ID 로만.

    현금및현금성자산이 없거나 단기 차입 계정이 하나도 없으면 사유를 표시한다 (차입이 없는
    회사와 계정을 못 찾은 경우를 구분할 수 없으므로 추정해 0 으로 그리지 않는다). 찾은 계정만
    그리며, 못 찾은 항목은 부제에 밝힌다.
    """
    title = "유동성 (현금 vs 단기 차입)"
    accounts = data["accounts"]
    if _account(accounts, "cash") is None:
        return ChartGap(title, "현금및현금성자산 계정을 DART 표준 계정 ID 로 찾지 못했습니다.")
    assets = [(label, v) for key, label in _LIQUIDITY_ASSETS if (v := _account(accounts, key)) is not None]
    debts = [(label, v) for key, label in _LIQUIDITY_DEBTS if (v := _account(accounts, key)) is not None]
    if not debts:
        return ChartGap(title, "단기차입금·유동성장기부채·유동성전환사채 계정을 DART 표준 계정 ID 로 찾지 못했습니다 "
                               "(차입이 없는 회사이거나 다른 계정을 쓰는 회사일 수 있습니다).")
    steps = [(name, v, "asset") for name, v in assets] + [(name, v, "debt") for name, v in debts]
    scale = _won_scale([v for _, v, _ in steps])
    cash_total, debt_total = sum(v for _, v in assets), sum(v for _, v in debts)
    divisor, unit_label, digits = scale
    coverage = f"현금성 {cash_total / divisor:,.{digits}f} vs 단기 차입 {debt_total / divisor:,.{digits}f}"
    missing = [label for key, label in (*_LIQUIDITY_ASSETS, *_LIQUIDITY_DEBTS) if _account(accounts, key) is None]
    note = f"{_financial_note(data)} · 초록=현금성 자산, 빨강=단기 차입 · {coverage}"
    if missing:
        note += f" · 보고서에서 찾지 못한 항목: {', '.join(missing)}"
    chart = waterfall_chart(title, steps, note=note, scale=scale)
    return chart or ChartGap(title, "그릴 계정이 없습니다.")


def build_financial_charts(fundamentals_data: dict[str, str] | None) -> list[Chart | ChartGap]:
    """재무 분석가가 보존한 핵심 계정(``fundamentals_data["accounts"]``)으로 재무 차트를 만든다.

    ``fundamentals_data`` 가 없으면 (예전 run) 빈 리스트. DART 조회 실패·재무제표 없음은 세
    차트 모두 사유로 표시한다. 계정을 찾지 못한 차트는 추정하지 않고 어떤 계정이 없는지 밝힌다.
    """
    if not fundamentals_data or "accounts" not in fundamentals_data:
        return []
    text = fundamentals_data.get("accounts") or ""
    data = parse_financial_accounts(text)
    if data is None:
        first = text.strip().splitlines()[0][:160] if text.strip() else ""
        reason = first or "재무제표 데이터가 없어 그리지 못했습니다."
        return [ChartGap(t, reason) for t in ("손익 폭포", "현금 흐름 브리지", "유동성 (현금 vs 단기 차입)")]
    return [income_waterfall(data), cash_bridge(data), liquidity_chart(data)]
