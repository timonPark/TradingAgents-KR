"""#139: KRX 로그인 세션 유닛 테스트.

실제 KRX 호출 금지 — ``requests.Session`` 을 모킹. 실호출은 ``-m integration``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from tradingagents.dataflows.errors import VendorNotConfiguredError, VendorUnavailableError
from tradingagents.dataflows.vendors import krx_session

PASSWORD = "very-secret-pw"
SESSION_CLS = "tradingagents.dataflows.vendors.krx_session.requests.Session"


@pytest.fixture(autouse=True)
def _clean_state():
    krx_session.reset()
    yield
    krx_session.reset()


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("KRX_ID", "tester")
    monkeypatch.setenv("KRX_PW", PASSWORD)


def _fake_session(*login_codes):
    """로그인 POST 가 ``login_codes`` 를 순서대로 돌려주는 가짜 ``requests.Session``."""
    session = MagicMock(name="session")
    responses = []
    for code in login_codes:
        resp = MagicMock()
        resp.json.return_value = {"_error_code": code, "_error_message": "msg-" + code}
        responses.append(resp)
    session.post.side_effect = responses
    return session


# ---------- 자격증명 ----------

@pytest.mark.unit
def test_missing_credentials_raises_not_configured_without_network(monkeypatch):
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)
    with patch(SESSION_CLS) as cls, pytest.raises(VendorNotConfiguredError, match="KRX_ID"):
        krx_session.get_session()
    cls.assert_not_called()


# ---------- 로그인 성공 / 재사용 ----------

@pytest.mark.unit
def test_login_success_posts_credentials_and_returns_session(creds):
    fake = _fake_session("CD001")
    with patch(SESSION_CLS, return_value=fake):
        session = krx_session.get_session()
    assert session is fake
    assert fake.get.call_count == 2  # 초기 세션 + login.jsp
    payload = fake.post.call_args.kwargs["data"]
    assert payload["mbrId"] == "tester" and payload["pw"] == PASSWORD
    assert "skipDup" not in payload


@pytest.mark.unit
def test_session_is_reused_within_ttl(creds):
    fake = _fake_session("CD001")
    with patch(SESSION_CLS, return_value=fake):
        first = krx_session.get_session()
        second = krx_session.get_session()
    assert first is second
    assert fake.post.call_count == 1


@pytest.mark.unit
def test_session_is_refreshed_after_expiry(creds, monkeypatch):
    first, second = _fake_session("CD001"), _fake_session("CD001")
    with patch(SESSION_CLS, side_effect=[first, second]):
        krx_session.get_session()
        monkeypatch.setattr(krx_session, "_expires_at", 0.0)
        assert krx_session.get_session() is second
    first.close.assert_called()


@pytest.mark.unit
def test_duplicate_login_retries_once_with_skip_dup(creds):
    fake = _fake_session("CD011", "CD001")
    with patch(SESSION_CLS, return_value=fake):
        krx_session.get_session()
    assert fake.post.call_count == 2
    assert fake.post.call_args.kwargs["data"]["skipDup"] == "Y"


# ---------- 계정 잠금 방지: 거부되면 재시도하지 않는다 ----------

@pytest.mark.unit
@pytest.mark.parametrize("code", ["CD007", "CD010", "CD002"])
def test_rejected_credentials_raise_and_are_never_retried(creds, code):
    fake = _fake_session(code)
    with patch(SESSION_CLS, return_value=fake):
        with pytest.raises(krx_session.KrxLoginError) as first:
            krx_session.get_session()
        with pytest.raises(krx_session.KrxLoginError) as second:
            krx_session.get_session()
    assert first.value.code == code
    assert second.value is first.value
    assert fake.post.call_count == 1  # 두 번째 호출은 네트워크에 가지 않음


@pytest.mark.unit
def test_failed_duplicate_retry_is_also_remembered(creds):
    fake = _fake_session("CD011", "CD007")
    with patch(SESSION_CLS, return_value=fake):
        with pytest.raises(krx_session.KrxLoginError):
            krx_session.get_session()
        with pytest.raises(krx_session.KrxLoginError):
            krx_session.get_session()
    assert fake.post.call_count == 2


@pytest.mark.unit
def test_network_error_is_not_remembered_and_can_retry(creds):
    broken = MagicMock()
    broken.get.side_effect = requests.ConnectionError("boom")
    good = _fake_session("CD001")
    with patch(SESSION_CLS, side_effect=[broken, good]):
        with pytest.raises(krx_session.KrxLoginError):
            krx_session.get_session()
        assert krx_session.get_session() is good


@pytest.mark.unit
def test_error_messages_do_not_leak_password(creds):
    fake = _fake_session("CD007")
    with patch(SESSION_CLS, return_value=fake), pytest.raises(krx_session.KrxLoginError) as exc:
        krx_session.get_session()
    assert PASSWORD not in str(exc.value)

    krx_session.reset()
    broken = MagicMock()
    broken.get.side_effect = requests.ConnectionError(f"failed with {PASSWORD}")
    with patch(SESSION_CLS, return_value=broken), pytest.raises(krx_session.KrxLoginError) as exc2:
        krx_session.get_session()
    assert PASSWORD not in str(exc2.value)
    assert exc2.value.__cause__ is None


@pytest.mark.unit
def test_non_json_login_response_raises(creds):
    fake = MagicMock()
    bad = MagicMock()
    bad.json.side_effect = ValueError("not json")
    fake.post.return_value = bad
    with patch(SESSION_CLS, return_value=fake), pytest.raises(
        VendorUnavailableError, match="JSON"
    ):
        krx_session.get_session()


# ---------- pykrx 연결 ----------

@pytest.mark.unit
def test_authenticated_pykrx_swaps_and_restores_webio_requests(creds):
    from pykrx.website.comm import webio

    original = webio.requests
    fake = _fake_session("CD001")
    with patch(SESSION_CLS, return_value=fake):
        with krx_session.authenticated_pykrx():
            assert webio.requests is not original
        assert webio.requests is original


@pytest.mark.unit
def test_authenticated_pykrx_restores_even_when_block_raises(creds):
    from pykrx.website.comm import webio

    original = webio.requests
    with patch(SESSION_CLS, return_value=_fake_session("CD001")), pytest.raises(
        RuntimeError
    ), krx_session.authenticated_pykrx():
        raise RuntimeError("pykrx failed")
    assert webio.requests is original


@pytest.mark.unit
def test_authenticated_pykrx_does_not_touch_webio_when_login_fails(creds):
    from pykrx.website.comm import webio

    original = webio.requests
    with patch(SESSION_CLS, return_value=_fake_session("CD007")), pytest.raises(
        krx_session.KrxLoginError
    ), krx_session.authenticated_pykrx():
        pytest.fail("블록에 들어가면 안 된다")
    assert webio.requests is original


@pytest.mark.unit
def test_shim_sends_pykrx_requests_through_login_session(creds):
    """pykrx 의 ``Post.read`` 가 로그인 세션(쿠키 포함)으로 나가는지."""
    from pykrx.website.comm import webio

    fake = _fake_session("CD001")
    fake.post.side_effect = None
    data_resp = MagicMock()
    data_resp.json.return_value = {"output": []}
    # 로그인 POST 응답 다음에 데이터 POST 응답
    login_resp = MagicMock()
    login_resp.json.return_value = {"_error_code": "CD001"}
    fake.post.side_effect = [login_resp, data_resp]

    class _Req(webio.Post):
        @property
        def url(self):
            return "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

    with patch(SESSION_CLS, return_value=fake), krx_session.authenticated_pykrx():
        resp = _Req().read(bld="x", strtDd="20261029")

    assert resp is data_resp
    url = fake.post.call_args.args[0]
    assert url.endswith("getJsonData.cmd")
    assert fake.post.call_args.kwargs["data"] == {"bld": "x", "strtDd": "20261029"}
    assert fake.post.call_args.kwargs["headers"]["X-Requested-With"] == "XMLHttpRequest"


@pytest.mark.unit
def test_shim_upgrades_http_to_https(creds):
    """pykrx 1.0.x 는 ``http://`` 로 요청한다. KRX 는 이를 301 로 https 에 넘기는데
    그러면 POST 가 GET 으로 바뀌어 HTML 이 돌아온다 — 직접 https 로 보내야 한다."""
    from pykrx.website.comm import webio

    login_resp = MagicMock()
    login_resp.json.return_value = {"_error_code": "CD001"}
    fake = _fake_session("CD001")
    fake.post.side_effect = [login_resp, MagicMock(), MagicMock()]

    class _Req(webio.Post):
        @property
        def url(self):
            return "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"

    class _GetReq(webio.Get):
        @property
        def url(self):
            return "http://data.krx.co.kr/comm/bldAttendant/executeForResourceBundle.cmd"

    with patch(SESSION_CLS, return_value=fake), krx_session.authenticated_pykrx():
        _Req().read(bld="x")
        _GetReq().read(bld="x")

    assert fake.post.call_args.args[0].startswith("https://data.krx.co.kr/")
    assert fake.get.call_args.args[0].startswith("https://data.krx.co.kr/")


# ============================================================================
# Integration — 실제 KRX 로그인. KRX_ID/KRX_PW 필요. CI 는 skip.
#   로컬: ``pytest tests/test_krx_session.py -m integration``
#   주의: 로그인 시도는 1회뿐이며 거부되면 이후 재시도하지 않는다 (계정 잠금 방지).
# ============================================================================

@pytest.mark.integration
def test_live_login_and_investor_table():
    import os

    if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
        pytest.skip("KRX_ID/KRX_PW 미설정")
    from tradingagents.dataflows.vendors import pykrx

    df = pykrx._fetch_krx_investor_table("005930", "20261029", "20261104")
    assert "순매수" in df.columns
    assert "외국인" in df.index
