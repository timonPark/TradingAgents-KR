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

import os
from datetime import datetime
from typing import Any

_DART_INSTANCE: Any = None
_DART_INIT_ERROR: Exception | None = None


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
        from opendartreader import OpenDartReader
    except ImportError as exc:
        _DART_INIT_ERROR = RuntimeError(
            f"OpenDartReader 패키지가 설치되지 않았습니다: {exc}. "
            "`pip install OpenDartReader` 로 설치하세요."
        )
        raise _DART_INIT_ERROR from exc
    _DART_INSTANCE = OpenDartReader(api_key)
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


def _format_statement(df, division_code: str) -> str:
    """``finstate_all`` DataFrame 에서 특정 재무제표 섹션을 Markdown 표로 포맷."""
    if df is None or df.empty:
        return "조회된 데이터가 없습니다."
    sub = df[df["sj_div"] == division_code] if "sj_div" in df.columns else df
    if sub.empty:
        return f"{_FS_LABELS.get(division_code, division_code)} 섹션이 보고서에 포함되지 않았습니다."
    # 핵심 컬럼만 선택
    keep = [c for c in ("account_nm", "thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount") if c in sub.columns]
    if not keep:
        return str(sub.head(20))
    pretty = sub[keep].rename(columns={
        "account_nm": "계정",
        "thstrm_amount": "당기",
        "frmtrm_amount": "전기",
        "bfefrmtrm_amount": "전전기",
    }).head(30)
    return pretty.to_markdown(index=False)


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
        sections.append(_format_statement(df, "IS"))
        sections.append("### 재무상태표 요약")
        sections.append(_format_statement(df, "BS"))

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
    return header + _format_statement(df, "BS")


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
    return header + _format_statement(df, "CF")


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
    # 포괄손익(CIS)이 있으면 우선 사용, 없으면 손익계산서(IS)
    out = _format_statement(df, "CIS")
    if "데이터가 없습니다" in out or "포함되지 않았습니다" in out:
        out = _format_statement(df, "IS")
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
