"""Tests for deterministic instrument-identity resolution (#814) and the
context-anchored message placeholder (#888)."""

import unittest
from unittest.mock import patch

import pytest

from tradingagents.agents.context import (
    _identity,
    build_instrument_context,
    get_instrument_context_from_state,
    resolve_instrument_identity,
)


@pytest.mark.unit
class ResolveInstrumentIdentityTests(unittest.TestCase):
    def setUp(self):
        _identity.cache_clear()

    def test_resolves_company_metadata_from_dart(self):
        # Task 5b (#48): identity 는 DART 기업 프로필에서 가져옴 (KRX 전용 하드 포크).
        with patch("tradingagents.agents.context.get_company_profile") as mock:
            mock.return_value = {
                "longName": "삼성전자",
                "shortName": "Samsung Electronics",
                "exchange": "KOSPI",
                "quoteType": "EQUITY",
            }
            identity = resolve_instrument_identity("005930")
        mock.assert_called_once_with("005930")
        self.assertEqual(identity["company_name"], "삼성전자")
        self.assertEqual(identity["exchange"], "KOSPI")

    def test_falls_back_to_short_name(self):
        with patch("tradingagents.agents.context.get_company_profile") as mock:
            mock.return_value = {"shortName": "Samsung Electronics"}
            identity = resolve_instrument_identity("005930")
        self.assertEqual(identity["company_name"], "Samsung Electronics")

    def test_skips_placeholder_values(self):
        with patch("tradingagents.agents.context.get_company_profile") as mock:
            mock.return_value = {"longName": "  ", "exchange": "None"}
            identity = resolve_instrument_identity("005930")
        self.assertEqual(identity, {})

    def test_fails_open_on_exception(self):
        with patch(
            "tradingagents.agents.context.get_company_profile",
            side_effect=RuntimeError("rate limited"),
        ):
            self.assertEqual(resolve_instrument_identity("005930"), {})

    def test_a_failed_lookup_is_asked_again(self):
        # A long process (a backtest) must not run every later cell without an
        # identity because one request failed.
        call_count = {"n": 0}

        def side_effect(ticker):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise TimeoutError()
            return {"longName": "삼성전자"}

        with patch("tradingagents.agents.context.get_company_profile", side_effect=side_effect):
            self.assertEqual(resolve_instrument_identity("005930"), {})
            self.assertEqual(resolve_instrument_identity("005930")["company_name"], "삼성전자")

    def test_result_is_cached(self):
        with patch("tradingagents.agents.context.get_company_profile") as mock:
            mock.return_value = {"longName": "삼성전자"}
            first = resolve_instrument_identity("005930")
            second = resolve_instrument_identity("005930")
        mock.assert_called_once()  # second call served from cache
        self.assertEqual(first, second)


@pytest.mark.unit
class BuildInstrumentContextTests(unittest.TestCase):
    def test_mentions_exact_symbol_without_identity(self):
        context = build_instrument_context("7203.T")
        self.assertIn("7203.T", context)
        self.assertIn("exchange suffix", context)
        self.assertNotIn("Resolved identity", context)

    def test_injects_resolved_identity(self):
        context = build_instrument_context(
            "TOTDY", "stock",
            {
                "company_name": "TOTO LTD.",
                "sector": "Industrials",
                "industry": "Building Products & Equipment",
                "exchange": "PNK",
            },
        )
        self.assertIn("Company: TOTO LTD.", context)
        self.assertIn("Industrials / Building Products & Equipment", context)
        self.assertIn("Exchange: PNK", context)
        self.assertIn("Do not substitute a different company", context)

    def test_crypto_uses_name_label_and_keeps_hint(self):
        context = build_instrument_context(
            "BTC-USD", "crypto", {"company_name": "Bitcoin USD"}
        )
        self.assertIn("Name: Bitcoin USD", context)
        self.assertIn("crypto asset rather than a company", context)


@pytest.mark.unit
class GetInstrumentContextFromStateTests(unittest.TestCase):
    def test_prefers_precomputed_context(self):
        state = {"company_of_interest": "TOTDY", "instrument_context": "PRECOMPUTED"}
        self.assertEqual(get_instrument_context_from_state(state), "PRECOMPUTED")

    def test_fallback_is_network_free_ticker_only(self):
        # No instrument_context and no DART call — must not hit the network.
        with patch("tradingagents.agents.context.get_company_profile") as mock:
            context = get_instrument_context_from_state(
                {"company_of_interest": "005930", "asset_type": "stock"}
            )
        mock.assert_not_called()
        self.assertIn("005930", context)

    def test_fallback_respects_asset_type(self):
        context = get_instrument_context_from_state(
            {"company_of_interest": "BTC-USD", "asset_type": "crypto"}
        )
        self.assertIn("crypto asset", context)


if __name__ == "__main__":
    unittest.main()
