import logging

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.vendors.dart import (
    get_balance_sheet as get_dart_balance_sheet,
    get_cashflow as get_dart_cashflow,
    get_convertible_bonds as get_dart_convertible_bonds,
    get_fundamentals as get_dart_fundamentals,
    get_income_statement as get_dart_income_statement,
    get_insider_transactions as get_dart_insider_transactions,
)
from tradingagents.dataflows.vendors.ecos import get_macro_data as get_ecos_macro_data
from tradingagents.dataflows.vendors.naver_news import (
    get_global_news as get_naver_global_news,
    get_news as get_naver_news,
)
from tradingagents.dataflows.vendors.pykrx import (
    get_investor_net_purchases as get_pykrx_investor_net_purchases,
    get_stock_data as get_pykrx_stock_data,
    get_stock_stats_indicators_window as get_pykrx_indicators_window,
)

logger = logging.getLogger(__name__)

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data (KRX via pykrx)",
        "tools": [
            "get_stock_data",
            # Task 6b (#53): KRX 전용 투자자별 수급 — 외국인/기관/개인 순매수. 가격
            # 변동 선행 지표라 core 가격 범주에 포함.
            "get_investor_net_purchases",
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators (stockstats on pykrx OHLCV)",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement",
            "get_convertible_bonds",
            # Task 5b (#48): DART 주요주주/임원 지분변동은 공시 데이터 ― news 가 아닌
            # 재무/공시 범주. 상류는 Yahoo 뉴스 피드를 통해 insider 를 가져왔기 때문에
            # news_data 에 있었음.
            "get_insider_transactions",
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
        ]
    },
    "macro_data": {
        "description": "Macroeconomic indicators (rates, inflation, labor, growth)",
        "tools": [
            "get_macro_indicators",
        ]
    },
}

# Optional enrichment categories. These add macro context to the news analyst but
# are not core to a decision, so a vendor failure here degrades to a sentinel
# instead of aborting the run (a bad LLM-supplied indicator, a missing key, or a
# network blip should not crash an analysis over flavour data). Core categories
# (prices, fundamentals, news) still raise so a broken primary is loud.
# Task 7e (#66): prediction_markets 범주는 하드 포크 (ADR-0001) 로 삭제됨 — 한국
# 시장에 Polymarket 등가체가 없어 분석가가 활용할 기반이 없었음.
OPTIONAL_CATEGORIES = {"macro_data"}

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis — Task 6 (#51): KRX 전용 pykrx 단일 vendor
    "get_stock_data": {
        "pykrx": get_pykrx_stock_data,
    },
    "get_investor_net_purchases": {
        "pykrx": get_pykrx_investor_net_purchases,
    },
    # technical_indicators — pykrx OHLCV 에 stockstats 적용
    "get_indicators": {
        "pykrx": get_pykrx_indicators_window,
    },
    # fundamental_data — DART (금융감독원 Open DART) 단일 vendor (Task 5, KRX 전용 하드 포크)
    "get_fundamentals": {
        "dart": get_dart_fundamentals,
    },
    "get_balance_sheet": {
        "dart": get_dart_balance_sheet,
    },
    "get_cashflow": {
        "dart": get_dart_cashflow,
    },
    "get_income_statement": {
        "dart": get_dart_income_statement,
    },
    "get_convertible_bonds": {
        "dart": get_dart_convertible_bonds,
    },
    # news_data — Task 7c (#64): KRX 전용 네이버 금융 뉴스 단일 vendor
    "get_news": {
        "naver_news": get_naver_news,
    },
    "get_global_news": {
        "naver_news": get_naver_global_news,
    },
    "get_insider_transactions": {
        "dart": get_dart_insider_transactions,
    },
    # macro_data — Task 7d (#65): KRX 전용 한국은행 ECOS 단일 vendor
    "get_macro_indicators": {
        "ecos": get_ecos_macro_data,
    },
}


def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")


def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")


def vendor_unavailable(method: str, error: Exception) -> str:
    """What a call returns when every vendor was throttled or unreachable."""
    return (
        f"DATA_UNAVAILABLE: no configured vendor could serve {method} right now "
        f"({error}). This says nothing about the instrument; report the "
        f"data as unavailable and do not estimate or fabricate values."
    )


def no_data_available(error: NoMarketDataError) -> str:
    """What a call returns when every vendor that answered had no usable data."""
    resolved = "" if error.canonical == error.symbol else f" (resolved to '{error.canonical}')"
    # Surface the typed error's detail (e.g. "latest row is 2025-06-11 ...
    # stale") so the agent sees the specific reason — invalid symbol, no
    # coverage, or stale data — not just a generic "unavailable".
    reason = f" ({error.detail})" if error.detail else ""
    return (
        f"NO_DATA_AVAILABLE: No usable market data for '{error.symbol}'{resolved} from "
        f"any configured vendor{reason}. The symbol may be invalid, delisted, "
        f"not covered, or the vendor returned stale data. Do not estimate or "
        f"fabricate values — report that data is unavailable for this symbol."
    )


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    all_available_vendors = list(VENDOR_METHODS[method].keys())

    # The configured vendor list IS the chain: we do NOT silently fall back to
    # vendors the user did not choose (#988/#289) — that returned data from an
    # unexpected source and caused cross-vendor inconsistencies. For multi-vendor
    # fallback, list them in order, e.g. data_vendors="yfinance,alpha_vantage".
    # The "default" sentinel (no explicit config) uses all available vendors.
    explicit = [v for v in primary_vendors if v and v != "default"]
    if explicit:
        vendor_chain = [v for v in explicit if v in VENDOR_METHODS[method]]
        if not vendor_chain:
            raise ValueError(
                f"Configured vendor(s) {explicit} not available for '{method}'. "
                f"Available: {all_available_vendors}."
            )
    else:
        vendor_chain = all_available_vendors

    last_no_data: NoMarketDataError | None = None
    last_unavailable: VendorUnavailableError | None = None
    failed: Exception | None = None     # a vendor that raised something untyped
    first_error: Exception | None = None
    for vendor in vendor_chain:
        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return impl_func(*args, **kwargs)
        except VendorUnavailableError as e:
            logger.warning("Vendor %r unavailable for %s: %s; trying next vendor.", vendor, method, e)
            # Kept so an all-unavailable chain can say the vendor was the
            # problem, rather than reporting nothing about the symbol.
            last_unavailable = e
            continue
        except VendorNotConfiguredError as e:
            logger.warning("Vendor %r not configured for %s; trying next vendor.", vendor, method)
            if first_error is None:
                first_error = e  # Surface it if no other vendor can serve the call.
            continue
        except NoMarketDataError as e:
            last_no_data = e  # No data here; another configured vendor may have it
            continue
        except Exception as e:
            # Don't let one vendor's failure crash the call when another can
            # serve it, but never swallow silently: a broken primary must be
            # visible in the logs (#989), not hidden behind a fallback's verdict.
            logger.warning("Vendor %r failed for %s: %s", vendor, method, e)
            if first_error is None:
                first_error = e
            failed = e
            continue

    # A vendor that throttled or failed the request never said whether it has
    # the symbol, so no other vendor's "no data" can speak for the whole chain:
    # report the vendors as the problem, not the instrument. It must not end
    # the run either.
    if last_unavailable is not None:
        return vendor_unavailable(method, last_unavailable)
    if failed is not None and last_no_data is not None:
        return vendor_unavailable(method, failed)

    # Every vendor that answered reported "no data": the symbol is genuinely unavailable.
    # Return one explicit, instructive sentinel rather than a vendor-specific
    # empty string, so the agent reports "unavailable" instead of inventing a
    # value. This takes precedence over incidental fallback errors.
    if last_no_data is not None:
        if first_error is not None:
            # A vendor also hit a real error; surface it in logs so the no-data
            # verdict can't hide a broken primary (network/auth/etc.).
            logger.warning(
                "Returning NO_DATA for %s, but a vendor errored earlier: %s",
                method, first_error,
            )
        return no_data_available(last_no_data)

    # No vendor returned data and none reported clean "no data" — surface the
    # first real error (e.g. the primary vendor's network failure). Optional
    # enrichment categories degrade to a sentinel instead, so flavour data can't
    # abort the run.
    if first_error is not None:
        if category in OPTIONAL_CATEGORIES:
            logger.warning("Optional %s unavailable for %s: %s", category, method, first_error)
            return (
                f"DATA_UNAVAILABLE: optional {category} could not be retrieved "
                f"({first_error}). Proceed without it; do not fabricate values."
            )
        raise first_error

    raise RuntimeError(f"No available vendor for '{method}'")
