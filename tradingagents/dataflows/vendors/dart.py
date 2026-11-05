"""DART (금융감독원 Open DART) vendor for KRX 상장사 재무/공시 조회.

Task 5a (#47): 상류의 SEC EDGAR / Alpha Vantage / Yahoo fundamentals vendor 를
한국 공시 전용 Open DART 로 교체합니다. ``OpenDartReader`` 라이브러리를 통해
6자리 KRX 종목코드로 사업보고서/분기보고서, 재무제표, 주요주주 지분변동,
전환사채(CB) 발행 내역 등을 가져옵니다.

### DART reprt_code 매핑
- ``11013`` 1분기 보고서 (Q1, 보통 5월경 공시)
- ``11012`` 반기 보고서 (Q2, 보통 8월경 공시)
- ``11014`` 3분기 보고서 (Q3, 보통 11월경 공시)
- ``11011`` 사업보고서 (연간, 보통 다음 해 3월경 공시)

### 반환 형식
LLM 이 바로 읽을 수 있도록 Markdown 또는 섹션별 포맷 문자열 반환. 에러나 데이터
없음은 사람 읽기 쉬운 설명으로 (분석가 fail-safe 선조회가 섹션 전체를 잃어도
run 자체는 완결되도록).

환경변수 ``DART_API_KEY`` 가 없으면 호출 시점에 명확한 에러 메시지. 모듈 import
자체는 성공해야 합니다 (CI/테스트가 키 없이도 돌 수 있도록).
"""

from __future__ import annotations

import importlib
import json
import math
import os
from datetime import datetime
from typing import Any

_DART_INSTANCE: Any = None
_DART_INIT_ERROR: Exception | None = None


def _resolve_opendartreader_class() -> type:
    """``OpenDartReader`` 클래스를 찾아 반환. 0.3+ (``opendartreader``) 와 0.2.x
    (``OpenDartReader``, ``__init__`` 가 ``sys.modules`` 를 class 로 교체) 패키지
    레이아웃을 모두 지원합니다. py3.13+ 환경은 0.3+ 로, 그 이전 py 버전은 0.2.x
    로 설치되므로 호환성을 한 모듈에서 흡수합니다.
    """
    try:
        mod = importlib.import_module("opendartreader")
        return mod.OpenDartReader
    except (ImportError, AttributeError):
        pass
    # 0.2.x 는 ``sys.modules['OpenDartReader']`` 를 OpenDartReader 클래스 자체로
    # 교체합니다 (`__init__.py` 참조). 따라서 import 결과가 바로 클래스.
    return importlib.import_module("OpenDartReader")


def _dart() -> Any:
    """``OpenDartReader`` 인스턴스를 lazy 생성해 재사용.

    환경변수 ``DART_API_KEY`` 가 없거나 라이브러리 import 가 실패하면 호출마다
    같은 에러를 올려 상위 레이어가 fail-safe 로 처리할 수 있도록 합니다.
    """
    global _DART_INSTANCE, _DART_INIT_ERROR
    if _DART_INSTANCE is not None:
        return _DART_INSTANCE
    if _DART_INIT_ERROR is not None:
        raise _DART_INIT_ERROR

    api_key = os.environ.get("DART_API_KEY", "").strip()
    if not api_key:
        _DART_INIT_ERROR = RuntimeError(
            "DART_API_KEY 환경변수가 설정되지 않았습니다. "
            "https://opendart.fss.or.kr/ 에서 인증키를 발급받아 .env 에 추가하세요."
        )
        raise _DART_INIT_ERROR
    try:
        cls = _resolve_opendartreader_class()
    except ImportError as exc:
        _DART_INIT_ERROR = RuntimeError(
            f"OpenDartReader 패키지가 설치되지 않았습니다: {exc}. "
            "`pip install OpenDartReader` 로 설치하세요."
        )
        raise _DART_INIT_ERROR from exc
    _DART_INSTANCE = cls(api_key)
    return _DART_INSTANCE


def _reset_for_tests() -> None:
    """테스트에서 lazy singleton 을 재초기화하기 위한 helper."""
    global _DART_INSTANCE, _DART_INIT_ERROR
    _DART_INSTANCE = None
    _DART_INIT_ERROR = None


# 분기 리포트 매핑 — 가장 최근 공시된 쪽부터 역순으로 fallback 하기 위한 순서.
_REPRT_CODES_BY_FREQ = {
    "quarterly": ("11014", "11012", "11013", "11011"),  # Q3 → H1 → Q1 → 연간
    "annual": ("11011", "11014", "11012", "11013"),     # 연간 → Q3 → H1 → Q1
}


def _target_year(curr_date: str) -> int:
    """``curr_date`` 기준으로 가장 최근 완결된 리포트 연도."""
    try:
        parsed = datetime.strptime(curr_date, "%Y-%m-%d").date()
    except ValueError:
        parsed = datetime.utcnow().date()
    # 3월 이전이면 전년도 사업보고서가 아직 공시되지 않았을 가능성이 큼. 1년 전부터
    # 시도하면서 fallback 하도록 다음 함수가 처리.
    return parsed.year


def _fetch_finstate(ticker: str, year: int, reprt_code: str) -> Any:
    """``finstate_all`` 호출 + 에러 흡수. 성공 시 DataFrame, 실패 시 None."""
    try:
        df = _dart().finstate_all(ticker, year, reprt_code)
    except Exception:  # noqa: BLE001 — vendor 에러는 상위에서 "no data" 로 처리
        return None
    if df is None or (hasattr(df, "empty") and df.empty):
        return None
    return df


def _latest_finstate(ticker: str, curr_date: str, freq: str):
    """``curr_date`` 기준 가장 최근 공시된 재무제표 (year, reprt_code, DataFrame)."""
    year = _target_year(curr_date)
    codes = _REPRT_CODES_BY_FREQ.get(freq, _REPRT_CODES_BY_FREQ["quarterly"])
    # 올해 → 작년 두 해를 돌면서 사용 가능한 가장 최근 리포트 찾기.
    for try_year in (year, year - 1, year - 2):
        for code in codes:
            df = _fetch_finstate(ticker, try_year, code)
            if df is not None:
                return try_year, code, df
    return None, None, None


_FS_LABELS = {
    "BS": "재무상태표",
    "CIS": "포괄손익계산서",
    "IS": "손익계산서",
    "CF": "현금흐름표",
    "SCE": "자본변동표",
}

_REPRT_LABELS = {
    "11011": "사업보고서(연간)",
    "11012": "반기보고서",
    "11013": "1분기보고서",
    "11014": "3분기보고서",
}


_STATEMENT_ROWS = 30  # 표 하나에 싣는 최대 행 수


def _money_text(raw: Any) -> str:
    """금액 셀 → ``1,234`` (소수는 2자리). 값이 없으면 ``-``."""
    value = _amount(raw)
    if value is None:
        return "-"
    return f"{int(value):,}" if value.is_integer() else f"{value:,.2f}"


def _has_cumulative(sub) -> bool:
    """누적 열(``thstrm_add_amount``)에 값이 있는가 — 반기·3분기 보고서의 손익 표."""
    if "thstrm_add_amount" not in sub.columns:
        return False
    return any(_amount(v) is not None for v in sub["thstrm_add_amount"])


def _key_first(sub, division_code: str):
    """핵심 계정(``_KEY_ACCOUNTS``)을 맨 앞에 두고 나머지는 원래 순서를 유지한다.

    DART 응답은 행 순서가 회사마다 달라, 앞에서 자르면 매출·영업이익이 잘릴 수 있다.
    """
    if "account_id" not in sub.columns:
        return sub
    order = {
        account_id: i
        for i, (_, account_id, divisions) in enumerate(_KEY_ACCOUNTS)
        if division_code in divisions
    }
    rank = sub["account_id"].map(lambda a: order.get(a, len(_KEY_ACCOUNTS)))
    return sub.assign(_rank=rank).sort_values("_rank", kind="stable").drop(columns="_rank")


def _period_note(division_code: str, reprt_code: str | None, cumulative: bool) -> str:
    """표 머리말 — 금액 단위와 각 열이 가리키는 기간."""
    report = _REPRT_LABELS.get(reprt_code or "", "")
    prefix = f"{report} · " if report else ""
    if division_code in _INCOME_DIVS and cumulative:
        return (
            f"_{prefix}금액 단위: 원. **당기(분기 3개월)** 는 해당 분기만, **누적** 은 연초부터 "
            "보고 기간 끝까지의 합계입니다. 현금흐름표의 '당기'는 누적 기준이므로 "
            "손익과 비교할 때는 **누적** 열을 쓰세요._"
        )
    if division_code in _INCOME_DIVS:
        return f"_{prefix}금액 단위: 원. '당기'는 연초부터 보고 기간 끝까지의 누적입니다._"
    if division_code == "CF":
        return f"_{prefix}금액 단위: 원. '당기'는 연초부터 보고 기간 끝까지의 누적입니다._"
    return f"_{prefix}금액 단위: 원. '당기'는 보고 기간 말 시점 잔액입니다._"


def _format_statement(df, division_code: str, reprt_code: str | None = None) -> str:
    """``finstate_all`` DataFrame 에서 특정 재무제표 섹션을 Markdown 표로 포맷.

    반기·3분기 보고서의 손익 표는 ``thstrm_amount`` 가 해당 분기 3개월치라, 누적 열과
    전년 동기 누적 열을 함께 보여 현금흐름표(누적)와 같은 기간으로 비교할 수 있게 한다.
    """
    if df is None or df.empty:
        return "조회된 데이터가 없습니다."
    sub = df[df["sj_div"] == division_code] if "sj_div" in df.columns else df
    if sub.empty:
        return f"{_FS_LABELS.get(division_code, division_code)} 섹션이 보고서에 포함되지 않았습니다."
    sub = _key_first(sub, division_code)
    cumulative = division_code in _INCOME_DIVS and _has_cumulative(sub)
    if cumulative:
        columns = {
            "account_nm": "계정",
            "thstrm_amount": "당기(분기 3개월)",
            "thstrm_add_amount": "누적",
            "frmtrm_add_amount": "전년 동기 누적",
        }
    else:
        columns = {
            "account_nm": "계정",
            "thstrm_amount": "당기",
            "frmtrm_amount": "전기",
            "bfefrmtrm_amount": "전전기",
        }
    keep = [c for c in columns if c in sub.columns]
    if len(keep) < 2:
        return str(sub.head(20))
    pretty = sub[keep].head(_STATEMENT_ROWS).copy()
    for column in keep[1:]:  # 금액 열: 지수 표기·nan 대신 천 단위 구분 정수로
        pretty[column] = pretty[column].map(_money_text)
    pretty = pretty.rename(columns=columns)
    note = _period_note(division_code, reprt_code, cumulative)
    return note + "\n\n" + pretty.to_markdown(index=False)


def get_fundamentals(ticker: str, curr_date: str, trade_date: str = "") -> str:
    """최근 사업보고서 기반 기업 개황 + 핵심 지표.

    Args:
        ticker: KRX 6자리 종목코드
        curr_date: 분석 기준일 (``YYYY-MM-DD``). 이 날짜 기준으로 가장 최근 공시된
            보고서를 가져옴.
        trade_date: 호환성을 위한 unused 매개변수 (분석가가 InjectedState 로 넘김).
    """
    try:
        dart = _dart()
    except Exception as exc:  # noqa: BLE001
        return f"[DART 조회 실패: {exc}]"

    sections: list[str] = []
    # 1. 기업 개황
    try:
        company = dart.company(ticker)
    except Exception as exc:  # noqa: BLE001
        company = None
        sections.append(f"**기업 개황**: 조회 실패 ({exc})")
    if company:
        sections.append("## 기업 개황")
        try:
            sections.append(_render_company_overview(company))
        except Exception as exc:  # noqa: BLE001
            sections.append(f"기업 개황 포맷 실패: {exc}")

    # 2. 최근 분기 핵심 지표 (손익/재무상태 요약)
    year, code, df = _latest_finstate(ticker, curr_date, "quarterly")
    if df is None:
        sections.append("## 최근 재무제표: 조회된 공시가 없습니다.")
    else:
        sections.append(
            f"## 최근 재무제표 ({year}년 {_REPRT_LABELS.get(code, code)})"
        )
        sections.append("### 손익계산서 요약")
        sections.append(_format_statement(df, "IS", code))
        sections.append("### 재무상태표 요약")
        sections.append(_format_statement(df, "BS", code))

    return "\n\n".join(sections) if sections else "조회된 공시가 없습니다."


def _render_company_overview(company: dict) -> str:
    """``dart.company()`` 결과 dict 를 Markdown 리스트로 포맷."""
    labels = (
        ("corp_name", "회사명"),
        ("corp_name_eng", "영문 회사명"),
        ("ceo_nm", "대표자명"),
        ("corp_cls", "법인 구분"),
        ("induty_code", "업종 코드"),
        ("est_dt", "설립일"),
        ("adres", "주소"),
        ("hm_url", "홈페이지"),
    )
    lines: list[str] = []
    for key, label in labels:
        value = company.get(key) if isinstance(company, dict) else None
        if value:
            lines.append(f"- **{label}**: {value}")
    return "\n".join(lines) if lines else "(세부 정보 없음)"


def get_balance_sheet(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
    trade_date: str = "",
) -> str:
    """재무상태표 Markdown 표. ``freq`` 는 ``"quarterly"`` 또는 ``"annual"``."""
    curr_date = curr_date or datetime.utcnow().strftime("%Y-%m-%d")
    try:
        _dart()
    except Exception as exc:  # noqa: BLE001
        return f"[DART 조회 실패: {exc}]"
    year, code, df = _latest_finstate(ticker, curr_date, freq)
    if df is None:
        return "조회된 재무상태표가 없습니다."
    header = f"**{year}년 {_REPRT_LABELS.get(code, code)}** 재무상태표\n\n"
    return header + _format_statement(df, "BS", code)


def get_cashflow(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
    trade_date: str = "",
) -> str:
    """현금흐름표 Markdown 표."""
    curr_date = curr_date or datetime.utcnow().strftime("%Y-%m-%d")
    try:
        _dart()
    except Exception as exc:  # noqa: BLE001
        return f"[DART 조회 실패: {exc}]"
    year, code, df = _latest_finstate(ticker, curr_date, freq)
    if df is None:
        return "조회된 현금흐름표가 없습니다."
    header = f"**{year}년 {_REPRT_LABELS.get(code, code)}** 현금흐름표\n\n"
    return header + _format_statement(df, "CF", code)


def get_income_statement(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
    trade_date: str = "",
) -> str:
    """손익계산서 Markdown 표."""
    curr_date = curr_date or datetime.utcnow().strftime("%Y-%m-%d")
    try:
        _dart()
    except Exception as exc:  # noqa: BLE001
        return f"[DART 조회 실패: {exc}]"
    year, code, df = _latest_finstate(ticker, curr_date, freq)
    if df is None:
        return "조회된 손익계산서가 없습니다."
    header = f"**{year}년 {_REPRT_LABELS.get(code, code)}** 손익계산서\n\n"
    # 손익계산서(IS)를 우선 사용한다. 두산에너빌리티처럼 IS 와 CIS 가 따로 있는 회사의 CIS 는
    # 기타포괄손익 항목뿐이라 매출·영업이익이 없다. IS 가 없는 회사(금호전기)만 CIS 로 대체.
    out = _format_statement(df, "IS", code)
    if "데이터가 없습니다" in out or "포함되지 않았습니다" in out:
        out = _format_statement(df, "CIS", code)
    return header + out


def get_insider_transactions(ticker: str, trade_date: str = "") -> str:
    """주요주주/임원 지분변동 요약 (DART `major_shareholders_exec`)."""
    try:
        dart = _dart()
    except Exception as exc:  # noqa: BLE001
        return f"[DART 조회 실패: {exc}]"
    try:
        df = dart.major_shareholders_exec(ticker)
    except Exception as exc:  # noqa: BLE001
        return f"[지분변동 조회 실패: {exc}]"
    if df is None or (hasattr(df, "empty") and df.empty):
        return "최근 지분변동 내역이 없습니다."
    try:
        keep = [c for c in ("repror", "isu_exctv_rgist_at", "sp_stock_lmp_cnt", "trde_dt") if c in df.columns]
        pretty = df[keep].head(30) if keep else df.head(30)
        return pretty.to_markdown(index=False)
    except Exception as exc:  # noqa: BLE001
        return f"[지분변동 포맷 실패: {exc}]"


def get_company_profile(ticker: str) -> dict:
    """``context.py`` 의 identity 해석을 위한 KRX 기업 프로필 dict.

    상류 `yahoo.fundamentals.get_company_profile` 과 같은 shape (``longName``,
    ``shortName``, ``exchange``, ``quoteType``) 를 돌려주지만 KRX corp_cls 를
    거래소 라벨 (KOSPI/KOSDAQ) 로 매핑. DART 호출 실패 시 빈 dict 반환해
    ``resolve_instrument_identity`` 가 안전하게 폴백.
    """
    try:
        company = _dart().company(ticker)
    except Exception:  # noqa: BLE001 — identity 해석 실패는 항상 fail-open
        return {}
    if not isinstance(company, dict):
        return {}
    name = (company.get("corp_name") or "").strip()
    name_eng = (company.get("corp_name_eng") or "").strip()
    corp_cls = (company.get("corp_cls") or "").strip()
    # DART `corp_cls` 코드 — Y: KOSPI, K: KOSDAQ, N: KONEX, E: 기타
    exchange_map = {"Y": "KOSPI", "K": "KOSDAQ", "N": "KONEX", "E": "기타"}
    return {
        "longName": name or name_eng,
        "shortName": name_eng or name,
        "exchange": exchange_map.get(corp_cls, corp_cls),
        "quoteType": "EQUITY",
    }


def get_convertible_bonds(ticker: str, trade_date: str = "") -> str:
    """최근 전환사채(CB) 발행 공시 목록 (Task 5 신규 KRX 전용 지표).

    DART ``list`` API 로 최근 6개월 공시를 가져와 "전환사채" 가 제목에 포함된
    것만 필터. CB 는 신주 발행 가능성이라 희석 리스크 평가에 중요.
    """
    try:
        dart = _dart()
    except Exception as exc:  # noqa: BLE001
        return f"[DART 조회 실패: {exc}]"
    try:
        today = datetime.utcnow().date()
        start = today.replace(year=today.year - 1)
        df = dart.list(ticker, start=start.strftime("%Y-%m-%d"), end=today.strftime("%Y-%m-%d"))
    except Exception as exc:  # noqa: BLE001
        return f"[공시 목록 조회 실패: {exc}]"
    if df is None or (hasattr(df, "empty") and df.empty):
        return "최근 1년간 공시가 없습니다."
    try:
        mask = df["report_nm"].astype(str).str.contains("전환사채") if "report_nm" in df.columns else None
        if mask is None:
            return "공시 포맷을 인식할 수 없어 CB 필터링을 건너뛰었습니다."
        cbs = df[mask]
        if cbs.empty:
            return "최근 1년간 전환사채(CB) 발행 공시가 없습니다."
        keep = [c for c in ("rcept_dt", "report_nm", "flr_nm") if c in cbs.columns]
        pretty = cbs[keep].rename(columns={
            "rcept_dt": "접수일",
            "report_nm": "보고서명",
            "flr_nm": "제출인",
        })
        return pretty.to_markdown(index=False)
    except Exception as exc:  # noqa: BLE001
        return f"[CB 공시 포맷 실패: {exc}]"


# ---------------------------------------------------------------------------
# 핵심 계정 구조화 (#149) — 보고서 재무 차트용
# ---------------------------------------------------------------------------

# 계정명(``account_nm``)은 회사마다 다르다 (``매출액`` / ``수익``, ``반기순이익`` /
# ``당기순이익(손실)``). 그래서 핵심 계정은 **DART 표준 계정 ID**(``account_id``)로 식별한다.
# (key, 표준 계정 ID, 찾을 재무제표 구분)  — 삼성전자·두산에너빌리티·금호전기 응답으로 확인.
_INCOME_DIVS = ("IS", "CIS")   # 손익계산서가 없는 회사는 포괄손익계산서(CIS)에 함께 있다
_KEY_ACCOUNTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("revenue", "ifrs-full_Revenue", _INCOME_DIVS),
    ("cost_of_sales", "ifrs-full_CostOfSales", _INCOME_DIVS),
    ("gross_profit", "ifrs-full_GrossProfit", _INCOME_DIVS),
    ("operating_income", "dart_OperatingIncomeLoss", _INCOME_DIVS),
    ("profit_before_tax", "ifrs-full_ProfitLossBeforeTax", _INCOME_DIVS),
    ("net_income", "ifrs-full_ProfitLoss", _INCOME_DIVS),
    ("cfo", "ifrs-full_CashFlowsFromUsedInOperatingActivities", ("CF",)),
    ("cfi", "ifrs-full_CashFlowsFromUsedInInvestingActivities", ("CF",)),
    ("cff", "ifrs-full_CashFlowsFromUsedInFinancingActivities", ("CF",)),
    ("fx_effect", "ifrs-full_EffectOfExchangeRateChangesOnCashAndCashEquivalents", ("CF",)),
    ("cash_begin", "dart_CashAndCashEquivalentsAtBeginningOfPeriodCf", ("CF",)),
    ("cash_end", "dart_CashAndCashEquivalentsAtEndOfPeriodCf", ("CF",)),
    # 재무상태표 — 유동성 차트 (#149). 단기 차입은 회사마다 표준 ID 가 다르다:
    #   두산에너빌리티·금호전기 ``ifrs-full_ShorttermBorrowings`` / 삼성전자 ``dart_CurrentLoansReceived``.
    # 같은 key 가 여러 줄이면 먼저 찾은 것만 쓴다 (합산하지 않는다).
    ("cash", "ifrs-full_CashAndCashEquivalents", ("BS",)),
    ("short_term_deposits", "ifrs-full_ShorttermDepositsNotClassifiedAsCashEquivalents", ("BS",)),
    ("short_borrowings", "ifrs-full_ShorttermBorrowings", ("BS",)),
    ("short_borrowings", "dart_CurrentLoansReceived", ("BS",)),
    ("current_long_term_debt", "ifrs-full_CurrentPortionOfLongtermBorrowings", ("BS",)),
    ("current_convertible_bonds", "dart_CurrentPortionOfConvertibleBonds", ("BS",)),
)

# 손익 항목은 누적 금액(``thstrm_add_amount``)을 쓴다: 반기·3분기 보고서의 ``thstrm_amount`` 는
# 해당 분기 3개월치라 현금흐름표(누적)와 기간이 다르다. 누적 금액이 없는 보고서(1분기·사업보고서)
# 는 ``thstrm_amount`` 가 곧 누적(= 해당 기간 전체)이다.
_PERIOD_LABELS = {
    "11013": "1분기 누적 (1~3월)",
    "11012": "반기 누적 (1~6월)",
    "11014": "3분기 누적 (1~9월)",
    "11011": "연간",
}


def _amount(raw: Any) -> float | None:
    """DART 금액 문자열(``'1,234'``/``'-5'``/빈 값/nan) → float. 해석 불가면 None."""
    if raw is None:
        return None
    if isinstance(raw, float) and math.isnan(raw):
        return None
    text = str(raw).replace(",", "").strip()
    if not text or text.lower() == "nan" or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _pick_amount(row: Any, division: str) -> float | None:
    cumulative = _amount(row.get("thstrm_add_amount")) if division in _INCOME_DIVS else None
    return cumulative if cumulative is not None else _amount(row.get("thstrm_amount"))


def extract_key_accounts(df: Any, year: int, reprt_code: str) -> dict[str, Any]:
    """``finstate_all`` DataFrame 에서 핵심 계정을 표준 계정 ID 로 뽑는다.

    같은 ID 가 손익계산서와 포괄손익계산서에 모두 있으면 손익계산서(IS)가 우선한다. 값이
    비어 있는 계정은 결과에서 뺀다 (0 으로 채우지 않는다).
    """
    accounts: dict[str, dict[str, Any]] = {}
    if df is not None and not getattr(df, "empty", True) and "account_id" in df.columns:
        for key, account_id, divisions in _KEY_ACCOUNTS:
            if key in accounts:      # 같은 key 의 앞선 표준 ID 로 이미 찾았다
                continue
            for division in divisions:
                rows = df[(df["account_id"] == account_id) & (df["sj_div"] == division)]
                if "account_detail" in rows.columns:   # 부문별(주석) 행이 아니라 본표 행
                    main = rows[rows["account_detail"].isin(["-", "", None])]
                    rows = main if not main.empty else rows
                for _, row in rows.iterrows():
                    value = _pick_amount(row, division)
                    if value is not None:
                        accounts[key] = {"name": str(row.get("account_nm", "")), "value": value}
                        break
                if key in accounts:
                    break
    return {
        "year": year,
        "reprt_code": reprt_code,
        "report": _REPRT_LABELS.get(reprt_code, reprt_code),
        "period": _PERIOD_LABELS.get(reprt_code, ""),
        "basis": "연결",     # finstate_all 을 CFS(연결)로 요청한다
        "unit": "원",
        "accounts": accounts,
    }


def get_financial_accounts(ticker: str, curr_date: str, trade_date: str = "") -> str:
    """보고서 차트용 핵심 계정(JSON). 표준 계정 ID 로 식별한 값만 담는다 (#149).

    성공하면 ``{"year", "report", "period", "basis", "unit", "accounts": {key: {name, value}}}``
    JSON 문자열. 실패·데이터 없음은 다른 DART 함수처럼 사람이 읽는 문구를 돌려준다.
    """
    try:
        _dart()
    except Exception as exc:  # noqa: BLE001
        return f"[DART 조회 실패: {exc}]"
    year, code, df = _latest_finstate(ticker, curr_date, "quarterly")
    if df is None:
        return "조회된 재무제표가 없습니다."
    return json.dumps(extract_key_accounts(df, year, code), ensure_ascii=False)


# ---------------------------------------------------------------------------
# 회사 개요 (#163) — 사업보고서 "1. 사업의 개요" 원문 발췌. 모델이 학습 지식으로 지어내지 않도록
# 1차 자료(공시)를 그대로 가져오고, 보고서에는 출처를 함께 표기한다.
# ---------------------------------------------------------------------------

_OVERVIEW_MAX_CHARS = 1800
_MARKET_BY_CLS = {"Y": "KOSPI", "K": "KOSDAQ", "N": "KONEX"}
_BLOCK_END = ("</p>", "</tr>", "</div>", "</li>", "<br>", "<br/>", "<br />")
_INLINE_TAG = r"</?(?:b|i|u|em|strong|span|font|a|sup|sub)\b[^>]*>"   # 글자 사이에 공백을 만들지 않는 태그


def _table_rows(table_markup: str) -> str:
    """``<table>`` → 행마다 한 줄, 셀은 `` | `` 로 잇는다 (셀 안의 문단 태그로 줄이 갈라지지 않게)."""
    import html as html_lib
    import re

    rows = []
    for row in re.findall(r"<tr\b.*?</tr>", table_markup, flags=re.S | re.I):
        cells = []
        for cell in re.findall(r"<t[dh]\b.*?</t[dh]>", row, flags=re.S | re.I):
            text = html_lib.unescape(re.sub(r"<[^>]+>", " ", re.sub(_INLINE_TAG, "", cell))).replace("\xa0", " ")
            cells.append(re.sub(r"\s+", " ", text).strip())
        if any(cells):
            rows.append(" | ".join(c for c in cells if c))
    return "\n" + "\n".join(rows) + "\n"


def _plain_text(markup: str) -> str:
    """DART 뷰어 HTML → 문단 구분이 남은 평문."""
    import html as html_lib
    import re

    text = re.sub(_INLINE_TAG, "", markup, flags=re.I)
    text = re.sub(r"<table\b.*?</table>", lambda m: _table_rows(m.group(0)), text, flags=re.S | re.I)
    for cell in ("</td>", "</th>"):     # 표 한 줄이 셀마다 갈라지지 않게
        text = text.replace(cell, " | ").replace(cell.upper(), " | ")
    for tag in _BLOCK_END:
        text = text.replace(tag, "\n").replace(tag.upper(), "\n")
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip(" |\r\t") for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _trim_overview(text: str, limit: int = _OVERVIEW_MAX_CHARS) -> str:
    """문장 경계에서 자른다. 잘렸으면 끝에 표시를 단다."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = max(cut.rfind("다. "), cut.rfind("다.\n"), cut.rfind(".\n"))
    if boundary > limit * 0.5:
        cut = cut[: boundary + 2]
    return cut.rstrip() + " …(이하 생략)"


def _latest_business_report(ticker: str, curr_date: str) -> tuple[Any, str, str] | None:
    """분석 기준일 이전에 공시된 가장 최근 정기보고서 (사업보고서 우선): (행, 접수번호, 보고서명)."""
    try:
        end = datetime.strptime(curr_date, "%Y-%m-%d").date()
    except ValueError:
        end = datetime.utcnow().date()
    start = end.replace(year=end.year - 2)
    listing = _dart().list(ticker, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), kind="A")
    if listing is None or getattr(listing, "empty", True) or "report_nm" not in listing.columns:
        return None
    rows = listing.sort_values("rcept_dt", ascending=False)
    annual = rows[rows["report_nm"].astype(str).str.contains("사업보고서")]
    chosen = annual if not annual.empty else rows
    row = chosen.iloc[0]
    return row, str(row["rcept_no"]), str(row["report_nm"])


def get_business_overview(ticker: str, curr_date: str, trade_date: str = "") -> str:
    """회사 개요(JSON): 기업 개황 + 사업보고서 "사업의 개요" 원문 발췌와 출처 (#163).

    성공하면 ``{"company_name", "market", "ceo", "established", "homepage", "report",
    "rcept_no", "source_url", "overview"}`` JSON 문자열. 실패·공시 없음은 사람이 읽는 문구.
    """
    import re

    import requests

    try:
        _dart()
    except Exception as exc:  # noqa: BLE001
        return f"[DART 조회 실패: {exc}]"
    try:
        company = _dart().company(ticker) or {}
    except Exception:  # noqa: BLE001 — 개황이 없어도 사업 개요는 시도한다
        company = {}
    try:
        found = _latest_business_report(ticker, curr_date)
    except Exception as exc:  # noqa: BLE001
        return f"[DART 공시 목록 조회 실패: {exc}]"
    if found is None:
        return "조회된 정기보고서가 없습니다."
    _row, rcept_no, report_name = found
    try:
        docs = _dart().sub_docs(rcept_no, match="사업의 개요")
        if docs is None or getattr(docs, "empty", True):
            docs = _dart().sub_docs(rcept_no, match="사업의 내용")
        if docs is None or getattr(docs, "empty", True):
            return f"{report_name}에서 '사업의 개요' 항목을 찾지 못했습니다."
        url = str(docs.iloc[0]["url"])
        response = requests.get(url, timeout=30)
        response.encoding = "utf-8"
        text = _plain_text(response.text)
    except Exception as exc:  # noqa: BLE001
        return f"[사업의 개요 조회 실패: {type(exc).__name__}: {exc}]"
    # 항목 제목("II. 사업의 내용", "1. 사업의 개요")은 본문이 아니다.
    lines = text.split("\n")
    while lines and len(lines[0]) < 20 and "사업의" in lines[0]:
        lines.pop(0)
    body = "\n".join(lines).strip()
    if not body:
        return f"{report_name}의 '사업의 개요' 본문이 비어 있습니다."
    return json.dumps({
        "company_name": str(company.get("corp_name") or "").strip(),
        "market": _MARKET_BY_CLS.get(str(company.get("corp_cls") or "").strip(), ""),
        "ceo": str(company.get("ceo_nm") or "").strip(),
        "established": str(company.get("est_dt") or "").strip(),
        "homepage": str(company.get("hm_url") or "").strip(),
        "report": re.sub(r"^(?:\[[^\]]+\]\s*)+", "", report_name),   # "[첨부추가]" 같은 접수 구분 접두어는 뗀다
        "rcept_no": rcept_no,
        "source_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
        "overview": _trim_overview(body),
    }, ensure_ascii=False)
