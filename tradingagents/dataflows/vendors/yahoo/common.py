"""Yahoo 뉴스 호출의 공통 재시도. 가격/OHLCV/snapshot 경로는 Task 6e (#56) 에서
pykrx 로 교체되면서 삭제됐고, 뉴스 서브모듈만 Task 7 (네이버뉴스 전환) 전까지
유지됩니다.
"""

import logging
import time

import yfinance as yf
from yfinance.exceptions import YFPricesMissingError, YFRateLimitError

from tradingagents.dataflows.errors import VendorUnavailableError

logger = logging.getLogger(__name__)

# yfinance answers some failed requests with an empty result, which would read as
# "no data" for a symbol nobody checked; raised, the failure is reported as one.
yf.config.debug.hide_exceptions = False


def _answered_empty(exc: Exception) -> bool:
    """Whether Yahoo answered that it has nothing: no such symbol (HTTP 404), or a
    price window with no prices in it.

    yfinance raises YFPricesMissingError for that answer and also for an answer
    that was an error (an error status, or Yahoo describing a failure), so only
    a chart with no prices, or Yahoo saying the data does not exist, counts.
    A missing time zone is not an answer: yfinance reports a failed lookup the same way.
    """
    if isinstance(exc, YFPricesMissingError):
        reason = exc.yahoo_reason
        return "status_code" not in (exc.debug_info or "") and (
            reason is None or reason.startswith("Data doesn't exist"))
    return getattr(getattr(exc, "response", None), "status_code", None) == 404


def yf_retry(func, max_retries=3, base_delay=2.0):
    """Execute a yfinance call with exponential backoff on rate limits.

    yfinance raises YFRateLimitError on HTTP 429 responses but does not
    retry them internally, so this wrapper retries them. A rate limit that
    outlasts the retries, or any other exception, is raised as
    VendorUnavailableError: it failed in transit and says nothing about the
    symbol. Yahoo answering that it has nothing for the symbol returns None,
    an empty answer. ``func`` should build its own Ticker and make the request
    itself: a Ticker keeps a failed ``info`` fetch as done, so asking the same
    one again reads an empty profile.
    """
    for attempt in range(max_retries + 1):
        try:
            return func()
        except YFRateLimitError as exc:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Yahoo Finance rate limited, retrying in {delay:.0f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                raise VendorUnavailableError(
                    f"Yahoo Finance rate limited after {max_retries} retries: {exc}"
                ) from exc
        except Exception as exc:
            if _answered_empty(exc):
                return None
            raise VendorUnavailableError(f"Yahoo Finance request failed: {type(exc).__name__}") from exc
