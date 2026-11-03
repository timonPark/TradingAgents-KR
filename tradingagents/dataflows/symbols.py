"""KRX 종목코드 유효성 검증과 파일시스템 안전 가드.

TradingAgents-KR 포크는 한국거래소(KRX) 상장 종목만 지원합니다 (code_artifact.md
Task 4, 이슈 #41/#42). 상류의 미국/홍콩/상해/forex/crypto 심볼 변환 테이블은
전부 삭제되었습니다 — KRX 종목코드는 보통주/우선주/ETF/ETN 모두 ``^\\d{6}$`` 로
통일된 6자리 숫자 체계라 추가 매핑 없이 그대로 쓸 수 있습니다.

삭제된 상류 로직:
- ``_FOREX_CURRENCIES`` / ``_CRYPTO_BASES`` / ``_ALIASES`` 테이블
- ``_HK_CODE`` / ``_SHANGHAI_SH`` 정규식과 변환
- forex ``=X`` 접미사 자동 부여
- crypto ``-USD`` 정규화
- Yahoo-specific suffix 변환 (``.SH`` → ``.SS`` 등)
- ``normalize_symbol`` lenient shim (Task 6d/6e, #55/#56) — Yahoo/AV vendor
  삭제와 함께 소비자가 사라져 제거.

## 공개 함수

- ``validate_krx_ticker`` — 엄격한 KRX 6자리 숫자 검증. CLI 가 사용자 입력에서
  이것을 호출해 KRX 외 티커를 사전 차단.
- ``safe_ticker_component`` — 파일시스템 경로 안전 가드. 티커 외 run_id 등 비-
  티커 입력도 통과시키므로 KRX 검증보다 넓은 집합.
- ``crypto_base`` — 암호자산 식별 스텁 (항상 ``None``). Task 7 (reddit/
  stocktwits 삭제) 전까지 유지.
"""

from __future__ import annotations

import re

# KRX 종목코드: 6자리 숫자. 보통주 (005930 삼성전자), 우선주 (005935 삼성전자우),
# ETF (069500 KODEX 200), ETN (530001) 모두 동일 패턴.
_KRX_TICKER_RE = re.compile(r"^\d{6}$")

# 파일시스템 경로 안전 문자. 티커 외에 run_id, 체크포인트 이름 등 사용자 입력도
# 통과시키므로 KRX 티커보다 넓은 집합을 허용합니다. 상류와 호환되는 범위를
# 그대로 유지 (등호 ``=`` 와 플러스 ``+`` 포함) — KRX 티커 자체는 ``validate_
# krx_ticker`` 가 별도로 엄격 검증하므로 여기는 경로 안전만 책임.
_TICKER_PATH_RE = re.compile(r"^[A-Za-z0-9._\-\^=+]+$")


def validate_krx_ticker(raw: str) -> str:
    """KRX 종목코드로 엄격 검증. 6자리 숫자가 아니면 ``ValueError``.

    CLI 가 사용자 입력을 받아들일 때 이 함수로 사전 차단합니다. 상류의 미국/
    홍콩/상해/forex/crypto 심볼 (``AAPL``, ``0700.HK``, ``GC=F``, ``BTC-USD``)
    은 전부 거부됩니다 — 하드 포크(ADR-0001) 결정에 따라 KRX 외 시장은 지원
    하지 않습니다.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"KRX 종목코드는 비어있지 않은 문자열이어야 합니다: {raw!r}")
    s = raw.strip()
    if not _KRX_TICKER_RE.fullmatch(s):
        raise ValueError(
            f"KRX 종목코드는 6자리 숫자입니다 (예: 005930 삼성전자, "
            f"000660 SK하이닉스, 069500 KODEX 200). got {raw!r}"
        )
    return s


def crypto_base(raw: str) -> str | None:
    """항상 ``None``. KRX 포크에서는 암호자산을 식별하지 않습니다.

    상류의 StockTwits/Reddit vendor (Task 7 에서 삭제 예정) 가 이 함수를
    import 하므로 스텁으로 유지. Task 7 완료 시 vendor 와 함께 제거 가능.
    """
    return None


def safe_ticker_component(value: str, *, max_len: int = 32) -> str:
    """``value`` 가 파일시스템 경로에 안전하게 삽입 가능한지 검증.

    티커는 CLI 입력이나 LLM 툴 호출에서 흘러들어오는데, 둘 다 공격자 제어
    콘텐츠에 영향받을 수 있습니다 (예: 가져온 뉴스에 섞인 prompt injection).
    검증 없이 ``../../../etc/foo`` 같은 값이 ``os.path.join`` / ``Path /`` 에
    들어가면 캐시/체크포인트/결과 디렉터리를 이탈합니다.

    허용 패턴에 맞으면 ``value`` 를 그대로 반환, 아니면 ``ValueError``.
    티커 검증 자체는 ``validate_krx_ticker`` 가 담당합니다 — 여기는 **경로
    안전** 가드일 뿐이라 run_id 같은 비-티커 입력도 통과시킵니다.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"ticker must be a non-empty string, got {value!r}")
    if len(value) > max_len:
        raise ValueError(f"ticker exceeds {max_len} chars: {value!r}")
    if not _TICKER_PATH_RE.fullmatch(value):
        raise ValueError(
            f"ticker contains characters not allowed in a filesystem path: {value!r}"
        )
    # 위 정규식이 '.' 를 허용하므로 ``.``, ``..``, ``...`` 같은 값이 통과하지만,
    # 경로 컴포넌트로서는 상위 디렉터리로 이탈합니다. 점만으로 이루어진 값 거부.
    if set(value) == {"."}:
        raise ValueError(f"ticker cannot consist solely of dots: {value!r}")
    return value
