"""KRX 데이터포털(data.krx.co.kr) 로그인 세션 — 투자자별 수급용 (#139).

KRX 는 투자자별 거래실적 조회에 로그인을 요구한다. 로그인을 지원하는 pykrx 1.2.x 는
``pandas<3.0`` 을 요구해 이 프로젝트(pandas 3)에 설치할 수 없으므로, pykrx 1.0.x 는
그대로 두고 **우리가 로그인 세션을 만들어 pykrx 의 HTTP 요청에 붙인다**.

### 로그인 흐름 (pykrx 1.2.9 ``website/comm/auth.py`` 와 동일)
1. ``GET MDCCOMS001.cmd`` → 초기 JSESSIONID
2. ``GET login.jsp`` → iframe 세션 초기화
3. ``POST MDCCOMS001D1.cmd`` (``mbrId``/``pw``) → ``_error_code == "CD001"`` 이면 정상
4. ``CD011`` (중복 로그인) 이면 ``skipDup=Y`` 로 한 번 더 전송

### 계정 잠금 방지 (CD007)
- import 시점에 로그인하지 않는다. 수급을 실제로 조회할 때만 로그인한다.
- 자격증명이 **거부**되면(``CD001`` 아님) 그 결과를 프로세스 안에 기억하고 **다시
  시도하지 않는다**. 틀린 비밀번호로 반복 시도하면 KRX 계정이 잠긴다.
- 네트워크 오류는 인증 거부가 아니므로 기억하지 않는다 (다음 호출에서 재시도).
- 비밀번호·쿠키는 로그/예외 메시지에 넣지 않는다.

### pykrx 연결
pykrx 1.0.x 의 ``webio`` 는 모듈 전역 ``requests`` 를 직접 호출한다.
``authenticated_pykrx()`` 가 그 전역을 로그인 세션에 위임하는 shim 으로 바꿔 끼우고
끝나면 되돌린다 (락으로 직렬화).
"""

from __future__ import annotations

import logging
import os
import threading
import time
import types
from collections.abc import Iterator
from contextlib import contextmanager

import requests

from tradingagents.dataflows.errors import VendorNotConfiguredError, VendorUnavailableError

logger = logging.getLogger(__name__)

LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
LOGIN_JSP = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
LOGIN_URL = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
REFERER = "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd"
REQUEST_TIMEOUT = 20
SESSION_TTL = 3600  # 초 — KRX 세션 유효 시간 (pykrx 1.2.x 와 동일)
REFRESH_BUFFER = 300  # 만료 5분 전부터는 새로 로그인

_ENV_ID = "KRX_ID"
_ENV_PW = "KRX_PW"


class KrxLoginError(VendorUnavailableError):
    """KRX 로그인 실패. ``code`` 는 KRX 응답의 ``_error_code`` (없으면 빈 문자열)."""

    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.code = code


_lock = threading.RLock()          # 세션 생성/조회
_patch_lock = threading.RLock()    # pykrx webio 전역 교체 직렬화
_session: requests.Session | None = None
_expires_at: float = 0.0
_rejected: KrxLoginError | None = None  # 자격증명 거부 결과 — 재시도하지 않는다


def reset() -> None:
    """프로세스 안의 세션·거부 기록을 지운다 (테스트용)."""
    global _session, _expires_at, _rejected
    with _lock:
        _session = None
        _expires_at = 0.0
        _rejected = None


def get_credentials() -> tuple[str, str]:
    """(KRX_ID, KRX_PW). 없으면 ``VendorNotConfiguredError``."""
    login_id = os.environ.get(_ENV_ID, "").strip()
    login_pw = os.environ.get(_ENV_PW, "").strip()
    if not login_id or not login_pw:
        raise VendorNotConfiguredError(
            "KRX 로그인 자격증명이 없습니다 (KRX_ID / KRX_PW 환경변수 미설정). "
            "data.krx.co.kr 계정을 .env 에 추가하세요."
        )
    return login_id, login_pw


def _post_login(session: requests.Session, payload: dict[str, str]) -> dict:
    headers = {"User-Agent": USER_AGENT, "Referer": LOGIN_PAGE}
    resp = session.post(LOGIN_URL, data=payload, headers=headers, timeout=REQUEST_TIMEOUT)
    try:
        data = resp.json()
    except ValueError:
        raise KrxLoginError("KRX 로그인 응답이 JSON 이 아닙니다") from None
    return data if isinstance(data, dict) else {}


def _login(login_id: str, login_pw: str) -> requests.Session:
    """새 세션으로 로그인한다. 실패하면 ``KrxLoginError``.

    자격증명이 거부되면 호출자(``get_session``)가 그 사실을 기억해 재시도를 막는다.
    """
    session = requests.Session()
    try:
        session.get(LOGIN_PAGE, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        session.get(
            LOGIN_JSP,
            headers={"User-Agent": USER_AGENT, "Referer": LOGIN_PAGE},
            timeout=REQUEST_TIMEOUT,
        )
        payload = {
            "mbrNm": "", "telNo": "", "di": "", "certType": "",
            "mbrId": login_id, "pw": login_pw,
        }
        data = _post_login(session, payload)
        code = str(data.get("_error_code", ""))
        if code == "CD011":  # 중복 로그인 — 기존 세션을 끊고 로그인
            payload["skipDup"] = "Y"
            data = _post_login(session, payload)
            code = str(data.get("_error_code", ""))
    except requests.RequestException as exc:
        # 예외 메시지에 URL 만 담기고 자격증명은 담기지 않는다. 체인은 끊는다.
        session.close()
        raise KrxLoginError(f"KRX 로그인 네트워크 오류: {type(exc).__name__}") from None
    if code != "CD001":
        session.close()
        message = str(data.get("_error_message", ""))[:100]
        raise KrxLoginError(f"KRX 로그인 거부 ({code or '코드 없음'}): {message}", code=code)
    return session


def get_session() -> requests.Session:
    """로그인된 세션을 돌려준다 (유효하면 재사용).

    Raises:
        VendorNotConfiguredError: ``KRX_ID``/``KRX_PW`` 없음
        KrxLoginError: 로그인 실패. 자격증명 거부는 이후 호출에서 재시도하지 않는다.
    """
    global _session, _expires_at, _rejected
    with _lock:
        if _rejected is not None:
            raise _rejected
        if _session is not None and time.time() < _expires_at - REFRESH_BUFFER:
            return _session
        login_id, login_pw = get_credentials()
        if _session is not None:
            _session.close()
            _session = None
        try:
            _session = _login(login_id, login_pw)
        except KrxLoginError as exc:
            if exc.code:  # 서버가 자격증명을 거부함 → 재시도 금지
                _rejected = exc
                logger.warning("KRX 로그인 거부 (%s) — 이 프로세스에서는 재시도하지 않음", exc.code)
            raise
        _expires_at = time.time() + SESSION_TTL
        return _session


def _shim(session: requests.Session) -> types.SimpleNamespace:
    """pykrx webio 가 호출하는 ``requests.get/post`` 를 로그인 세션으로 위임."""

    def _merged(headers: dict | None) -> dict:
        merged = {"User-Agent": USER_AGENT, "Referer": REFERER, "X-Requested-With": "XMLHttpRequest"}
        merged.update(headers or {})
        return merged

    def _https(url: str) -> str:
        # pykrx 1.0.x 는 http:// 로 요청하는데 KRX 는 301 로 https 에 넘긴다.
        # 리다이렉트되면 POST 가 GET 으로 바뀌어 데이터 대신 HTML 이 온다.
        return "https://" + url[len("http://"):] if url.startswith("http://") else url

    def get(url, headers=None, params=None, **kwargs):
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        return session.get(_https(url), headers=_merged(headers), params=params, **kwargs)

    def post(url, headers=None, data=None, **kwargs):
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        return session.post(_https(url), headers=_merged(headers), data=data, **kwargs)

    return types.SimpleNamespace(get=get, post=post)


@contextmanager
def authenticated_pykrx() -> Iterator[None]:
    """블록 안의 pykrx(1.0.x) HTTP 요청이 KRX 로그인 세션으로 나가게 한다.

    로그인 실패 시 블록에 들어가기 전에 예외가 난다 (``get_session`` 참조).
    """
    from pykrx.website.comm import webio

    session = get_session()
    with _patch_lock:
        original = webio.requests
        webio.requests = _shim(session)
        try:
            yield
        finally:
            webio.requests = original
