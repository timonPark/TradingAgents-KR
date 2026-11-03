"""Tests that empty vendor results never become fabricated data.

Covers the route-to-vendor sentinel path: NoMarketDataError must become a single
explicit "NO_DATA_AVAILABLE" string so the agent never fabricates a price.

The Yahoo-specific cache-poisoning test (TestLoadOhlcvNoPoison) was removed in
Task 6e (#56) with yahoo/ohlcv.py — pykrx has no persistent OHLCV cache.
"""

import unittest
from unittest import mock

import pytest

from tradingagents.dataflows import router
from tradingagents.dataflows.errors import NoMarketDataError


@pytest.mark.unit
class TestRouteToVendorSentinel(unittest.TestCase):
    def test_no_data_from_vendor_returns_sentinel(self):
        # Task 6b (#53): pykrx 가 유일한 가격 vendor. NoMarketDataError 는
        # NO_DATA_AVAILABLE 센티넬로 변환되어야 함.
        def raises_no_data(symbol, *a, **k):
            raise NoMarketDataError(symbol, symbol, "no rows")

        patched = {"pykrx": raises_no_data}
        with mock.patch.dict(
            router.VENDOR_METHODS, {"get_stock_data": patched}, clear=False
        ):
            result = router.route_to_vendor(
                "get_stock_data", "999999", "2026-01-01", "2026-01-10"
            )
        self.assertIn("NO_DATA_AVAILABLE", result)
        self.assertIn("999999", result)
        self.assertIn("Do not estimate", result)


if __name__ == "__main__":
    unittest.main()
