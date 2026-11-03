"""Tests that empty vendor results never become fabricated data.

Covers two systematic fixes:
  - load_ohlcv must not cache an empty download (cache poisoning), and must
    raise NoMarketDataError instead of returning an empty frame.
  - route_to_vendor must convert NoMarketDataError into a single explicit
    "NO_DATA_AVAILABLE" sentinel after all vendors are exhausted.
"""

import os
import unittest
from unittest import mock

import pandas as pd
import pytest

from tradingagents.dataflows import router
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors.yahoo import common, ohlcv


@pytest.mark.unit
class TestLoadOhlcvNoPoison(unittest.TestCase):
    def setUp(self):
        self._tmp = os.path.join(os.path.dirname(__file__), "_tmp_cache")
        os.makedirs(self._tmp, exist_ok=True)
        set_config({"data_cache_dir": self._tmp})

    def tearDown(self):
        for f in os.listdir(self._tmp):
            os.remove(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_empty_download_raises_and_does_not_cache(self):
        empty = mock.Mock(history=mock.Mock(return_value=pd.DataFrame()))
        # Yahoo answers, so an empty download means the symbol has no data.
        reachable = mock.patch.object(common, "vendor_reachable", return_value=True)
        reachable.start()
        self.addCleanup(reachable.stop)
        with mock.patch.object(ohlcv.yf, "Ticker", return_value=empty), \
                self.assertRaises(NoMarketDataError):
            ohlcv.load_ohlcv("FAKE", "2026-01-01")
        # Nothing should have been written to the cache.
        self.assertEqual(os.listdir(self._tmp), [])

        # A second call must re-attempt the fetch (no poisoned cache served).
        with mock.patch.object(ohlcv.yf, "Ticker", return_value=empty) as dl2:
            with self.assertRaises(NoMarketDataError):
                ohlcv.load_ohlcv("FAKE", "2026-01-01")
            self.assertTrue(dl2.called)


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
