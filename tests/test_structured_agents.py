"""Tests for structured-output agents (Trader, Research Manager, Sentiment Analyst).

The Portfolio Manager has its own coverage in tests/test_memory_log.py
(which exercises the full memory-log → PM injection cycle).  This file
covers the parallel schemas, render functions, and graceful-fallback
behavior we added for the Trader, Research Manager, and Sentiment Analyst
so they share the same deterministic output shape.
"""

import inspect
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from tradingagents.agents.analysts.sentiment_analyst import create_sentiment_analyst
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.rating import display_rating
from tradingagents.agents.schemas import (
    SENTIMENT_BAND_KO,
    PortfolioDecision,
    PortfolioRating,
    ResearchPlan,
    SentimentBand,
    SentimentReport,
    TraderAction,
    TraderProposal,
    render_research_plan,
    render_sentiment_report,
    render_trader_proposal,
)
from tradingagents.agents.trader.trader import create_trader

# ---------------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderTraderProposal:
    """Task 9b (#81): Korean 디폴트에서는 한국어 라벨 (액션/근거/진입가/손절가/
    포지션 사이징/최종 거래 제안), 값 (BUY/HOLD/SELL) 은 영어 유지로 파서 호환성
    보존. 영어 fallback 은 별도 테스트에서 ``output_language="English"`` 로 덮어
    쓰고 검증.
    """

    def test_minimal_required_fields(self):
        p = TraderProposal(action=TraderAction.HOLD, reasoning="Balanced setup; no edge.")
        md = render_trader_proposal(p)
        assert "**액션**: 보유" in md
        assert "**근거**: Balanced setup; no edge." in md
        # 영어 가치/트레일링 라인은 파서/외부 grep 호환성 유지, 라벨만 한국어.
        assert "최종 거래 제안: **보유**" in md

    def test_optional_fields_included_when_present(self):
        p = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Strong technicals + fundamentals.",
            entry_price=189.5,
            stop_loss=178.0,
            position_sizing="6% of portfolio",
        )
        md = render_trader_proposal(p)
        assert "**액션**: 매수" in md
        assert "**진입가**: 189.5" in md
        assert "**손절가**: 178.0" in md
        assert "**포지션 사이징**: 6% of portfolio" in md
        assert "최종 거래 제안: **매수**" in md

    def test_optional_fields_are_named_as_not_provided(self):
        """An omitted line reads as a field nobody asked for; the reader cannot
        tell it from a level the trader declined to set."""
        p = TraderProposal(action=TraderAction.SELL, reasoning="Guidance cut.")
        md = render_trader_proposal(p)
        for field in ("진입가", "손절가", "포지션 사이징"):
            assert f"**{field}**: 제공되지 않음" in md
        assert "최종 거래 제안: **매도**" in md

    def test_english_output_language_uses_english_labels(self):
        """``output_language="English"`` 로 바꾸면 영어 라벨 fallback."""
        from tradingagents.dataflows.config import set_config

        set_config({"output_language": "English"})
        try:
            md = render_trader_proposal(
                TraderProposal(action=TraderAction.BUY, reasoning="r")
            )
            assert "**Action**: Buy" in md
            assert "**Entry Price**: not provided" in md
            assert "FINAL TRANSACTION PROPOSAL: **BUY**" in md
        finally:
            set_config({"output_language": "Korean"})


@pytest.mark.unit
class TestNullishFloatCoercion:
    """A weak LLM may write "None"/"N/A" into an optional float field (#1058);
    coerce those to None so the structured call validates instead of erroring."""

    def test_trader_nullish_strings_coerce_to_none(self):
        for sentinel in ("None", "N/A", "null", "-", "", "TBD"):
            p = TraderProposal(
                action=TraderAction.HOLD,
                reasoning="x",
                entry_price=sentinel,
                stop_loss=sentinel,
            )
            assert p.entry_price is None
            assert p.stop_loss is None

    def test_trader_real_numeric_string_still_parses(self):
        p = TraderProposal(action=TraderAction.BUY, reasoning="x", entry_price="189.5")
        assert p.entry_price == 189.5

    def test_pm_nullish_price_target_coerces_to_none(self):
        d = PortfolioDecision(
            rating=PortfolioRating.OVERWEIGHT,
            executive_summary="s",
            investment_thesis="t",
            price_target="N/A",
        )
        assert d.price_target is None

    def test_percentage_answer_to_a_price_field_becomes_none(self):
        # The Trader is asked for concrete levels and may answer a price field
        # with a distance ("15%"), which failed the whole proposal (#1288).
        # A percentage cannot be salvaged: 15% must not become a $15 stop.
        for pct in ("15%", " 7.5% ", "-10%"):
            p = TraderProposal(
                action=TraderAction.BUY,
                reasoning="x",
                entry_price=pct,
                stop_loss=pct,
            )
            assert p.entry_price is None
            assert p.stop_loss is None

    def test_human_formatted_price_is_reduced_to_its_number(self):
        p = TraderProposal(
            action=TraderAction.BUY,
            reasoning="x",
            entry_price="$1,234.50",
            stop_loss="1,180",
        )
        assert p.entry_price == 1234.50
        assert p.stop_loss == 1180.0

    def test_one_bad_field_no_longer_fails_the_whole_proposal(self):
        # Previously a single '15%' raised, forcing a free-text retry that lost
        # the action and reasoning; now the rest of the proposal survives.
        p = TraderProposal(
            action=TraderAction.SELL,
            reasoning="downgrade on margin compression",
            entry_price="612.40",
            stop_loss="15%",
        )
        assert p.action is TraderAction.SELL
        assert p.entry_price == 612.40
        assert p.stop_loss is None


@pytest.mark.unit
class TestRenderResearchPlan:
    """Task 9b (#81) + 9d (#83): Korean 디폴트 라벨 (추천/근거/전략적 조치). 값
    (Overweight 등) 영어 유지로 파서 호환.
    """

    def test_required_fields(self):
        p = ResearchPlan(
            recommendation=PortfolioRating.OVERWEIGHT,
            rationale="Bull case carried; tailwinds intact.",
            strategic_actions="Build position over two weeks; cap at 5%.",
        )
        md = render_research_plan(p)
        assert "**추천**: 비중 확대" in md
        assert "**근거**: Bull case carried" in md
        assert "**전략적 조치**: Build position" in md

    def test_all_5_tier_ratings_render(self):
        for rating in PortfolioRating:
            p = ResearchPlan(
                recommendation=rating,
                rationale="r",
                strategic_actions="s",
            )
            md = render_research_plan(p)
            assert f"**추천**: {display_rating(rating.value)}" in md


# ---------------------------------------------------------------------------
# Trader agent: structured happy path + fallback
# ---------------------------------------------------------------------------


def _make_trader_state():
    return {
        "company_of_interest": "NVDA",
        "investment_plan": "**Recommendation**: Buy\n**Rationale**: ...\n**Strategic Actions**: ...",
        "market_report": "Current price $189.5; 14-day ATR 4.2; support $178, resistance $196.",
    }


def _structured_trader_llm(captured: dict, proposal: TraderProposal | None = None):
    """Build a MagicMock LLM whose with_structured_output binding captures the
    prompt and returns a real TraderProposal so render_trader_proposal works.
    """
    if proposal is None:
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Strong setup.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or proposal
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
def test_invoke_structured_falls_back_when_result_is_none():
    # A thinking model can answer in plain text, leaving the parser with None.
    # That must fall back to free text, not crash on render(None) (#1051).
    from tradingagents.agents.structured import invoke_structured_or_freetext

    structured = MagicMock()
    structured.invoke.return_value = None
    plain = MagicMock()
    plain.invoke.return_value = MagicMock(content="FREETEXT")

    out = invoke_structured_or_freetext(
        structured, plain, "prompt", render=lambda r: r.rating, agent_name="t"
    )
    assert out == "FREETEXT"
    plain.invoke.assert_called_once()


@pytest.mark.unit
class TestTraderAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="AI capex cycle intact; institutional flows constructive.",
            entry_price=189.5,
            stop_loss=178.0,
            position_sizing="6% of portfolio",
        )
        llm = _structured_trader_llm(captured, proposal)
        trader = create_trader(llm)
        result = trader(_make_trader_state())
        plan = result["trader_investment_plan"]
        # Task 9b (#81): Korean 디폴트 라벨.
        assert "**액션**: 매수" in plan
        assert "**진입가**: 189.5" in plan
        assert "최종 거래 제안: **매수**" in plan
        # The same rendered markdown is also added to messages for downstream agents.
        assert plan in result["messages"][0].content

    def test_prompt_includes_investment_plan(self):
        captured = {}
        llm = _structured_trader_llm(captured)
        trader = create_trader(llm)
        trader(_make_trader_state())
        # Task 9d (#83): 트레이더 프롬프트가 한국어화됨 — "제안된 투자 계획" 섹션 확인.
        prompt = captured["prompt"]
        assert any("제안된 투자 계획" in m["content"] for m in prompt)

    def test_prompt_includes_market_report_for_price_levels(self):
        # #1167: the Trader must see the technical market report so entry/stop
        # levels are grounded in real price structure, not just the digested plan.
        # Task 9d (#83): 섹션 헤딩 한국어화 — "기술적 시장 보고서:" / "구체적 가격 수준".
        captured = {}
        trader = create_trader(_structured_trader_llm(captured))
        trader(_make_trader_state())
        user = " ".join(m["content"] for m in captured["prompt"] if m["role"] == "user")
        system = " ".join(m["content"] for m in captured["prompt"] if m["role"] == "system")
        assert "기술적 시장 보고서:" in user
        assert "14-day ATR 4.2" in user            # the actual report content reached the Trader
        assert "support $178, resistance $196" in user
        assert "구체적 가격 수준" in system

    def test_empty_market_report_omits_the_section_and_grounding(self):
        # #1167: when the market analyst wasn't selected the report is empty, so
        # don't tell the Trader to ground levels in a report it doesn't have.
        captured = {}
        state = _make_trader_state()
        state["market_report"] = ""
        create_trader(_structured_trader_llm(captured))(state)
        text = " ".join(m["content"] for m in captured["prompt"])
        assert "기술적 시장 보고서:" not in text
        assert "구체적 가격 수준" not in text
        assert "제안된 투자 계획" in text  # still present

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain_response = (
            "**Action**: Sell\n\nGuidance cut hits margins.\n\n"
            "FINAL TRANSACTION PROPOSAL: **SELL**"
        )
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain_response)
        trader = create_trader(llm)
        result = trader(_make_trader_state())
        assert result["trader_investment_plan"] == plain_response


# ---------------------------------------------------------------------------
# Research Manager agent: structured happy path + fallback
# ---------------------------------------------------------------------------


def _make_rm_state():
    return {
        "company_of_interest": "NVDA",
        "investment_debate_state": {
            "history": "Bull and bear arguments here.",
            "bull_history": "Bull says...",
            "bear_history": "Bear says...",
            "current_response": "",
            "count": 1,
        },
    }


def _structured_rm_llm(captured: dict, plan: ResearchPlan | None = None):
    if plan is None:
        plan = ResearchPlan(
            recommendation=PortfolioRating.HOLD,
            rationale="Balanced view across both sides.",
            strategic_actions="Hold current position; reassess after earnings.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or plan
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestResearchManagerAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        plan = ResearchPlan(
            recommendation=PortfolioRating.OVERWEIGHT,
            rationale="Bull case is stronger; AI tailwind intact.",
            strategic_actions="Build position gradually over two weeks.",
        )
        llm = _structured_rm_llm(captured, plan)
        rm = create_research_manager(llm)
        result = rm(_make_rm_state())
        ip = result["investment_plan"]
        # Task 9b/9d: Korean 라벨, 값 영어 유지.
        assert "**추천**: 비중 확대" in ip
        assert "**근거**: Bull case" in ip
        assert "**전략적 조치**: Build position" in ip

    def test_prompt_uses_5_tier_rating_scale(self):
        """The RM prompt must list all five tiers so the schema enum matches user expectations."""
        captured = {}
        llm = _structured_rm_llm(captured)
        rm = create_research_manager(llm)
        rm(_make_rm_state())
        prompt = captured["prompt"]
        for tier in ("Buy", "Overweight", "Hold", "Underweight", "Sell"):
            assert f"**{tier}**" in prompt, f"missing {tier} in prompt"

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain_response = "**Recommendation**: Sell\n\n**Rationale**: ...\n\n**Strategic Actions**: ..."
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain_response)
        rm = create_research_manager(llm)
        result = rm(_make_rm_state())
        assert result["investment_plan"] == plain_response


# ---------------------------------------------------------------------------
# Sentiment Analyst: schema, render, structured happy path + fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderSentimentReport:
    def test_header_contains_band_and_score(self):
        report = SentimentReport(
            overall_band=SentimentBand.BULLISH,
            overall_score=7.2,
            confidence="high",
            narrative="Source breakdown here.",
        )
        md = render_sentiment_report(report)
        assert "**전체 센티먼트:** **강세**" in md
        assert "(점수: 7.2/10)" in md

    def test_header_contains_confidence(self):
        report = SentimentReport(
            overall_band=SentimentBand.NEUTRAL,
            overall_score=5.0,
            confidence="low",
            narrative="Limited data.",
        )
        assert "**신뢰도:** 낮음" in render_sentiment_report(report)

    def test_narrative_preserved_in_output(self):
        narrative = "## Breakdown\n\nStockTwits: 70% bullish.\n\n| Signal | Direction |\n|---|---|\n| News | Neutral |"
        report = SentimentReport(
            overall_band=SentimentBand.MILDLY_BULLISH,
            overall_score=6.0,
            confidence="medium",
            narrative=narrative,
        )
        assert narrative in render_sentiment_report(report)

    def test_all_six_bands_render(self):
        for band in SentimentBand:
            report = SentimentReport(
                overall_band=band, overall_score=5.0,
                confidence="medium", narrative="n",
            )
            assert SENTIMENT_BAND_KO[band.value] in render_sentiment_report(report)

    def test_score_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            SentimentReport(
                overall_band=SentimentBand.BULLISH, overall_score=11.0,
                confidence="high", narrative="n",
            )


def _make_sentiment_state():
    return {
        "company_of_interest": "NVDA",
        "trade_date": "2026-01-15",
        "asset_type": "stock",
        "messages": [],
    }


def _structured_sentiment_llm(captured: dict, report: SentimentReport | None = None):
    """MagicMock LLM whose structured binding captures the prompt and returns
    a real SentimentReport so render_sentiment_report works."""
    if report is None:
        report = SentimentReport(
            overall_band=SentimentBand.BULLISH, overall_score=7.5,
            confidence="high",
            narrative="StockTwits 75% bullish. News constructive. Reddit upbeat.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or report
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestSentimentAnalystAgent:
    @pytest.fixture(autouse=True)
    def _stub_prefetched_sources(self, monkeypatch):
        """Stub the sources the analyst pre-fetches before prompting.

        Task 7c (#64): StockTwits/Reddit 소셜 소스는 제거됨. 네이버 금융 뉴스
        단일 소스만 stubbing 하면 됨.
        """
        from tradingagents.agents.analysts import sentiment_analyst as sentiment

        monkeypatch.setattr(sentiment.get_news, "func", lambda *a, **k: "news", raising=False)

    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        report = SentimentReport(
            overall_band=SentimentBand.MILDLY_BEARISH, overall_score=4.0,
            confidence="medium", narrative="Mixed signals across sources.",
        )
        analyst = create_sentiment_analyst(_structured_sentiment_llm(captured, report))
        sr = analyst(_make_sentiment_state())["sentiment_report"]
        assert "**전체 센티먼트:** **약한 약세**" in sr
        assert "(점수: 4.0/10)" in sr
        assert "Mixed signals across sources." in sr

    def test_sentiment_report_also_in_messages(self):
        captured = {}
        analyst = create_sentiment_analyst(_structured_sentiment_llm(captured))
        result = analyst(_make_sentiment_state())
        assert len(result["messages"]) == 1
        assert result["sentiment_report"] == result["messages"][0].content

    def test_prompt_contains_ticker(self):
        captured = {}
        create_sentiment_analyst(_structured_sentiment_llm(captured))(_make_sentiment_state())
        assert any("NVDA" in str(m) for m in captured["prompt"])

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain = "**Overall Sentiment:** **Bearish** (Score: 3.0/10)\n**Confidence:** Low\n\nLimited data."
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain)
        assert create_sentiment_analyst(llm)(_make_sentiment_state())["sentiment_report"] == plain

    def test_falls_back_to_freetext_when_structured_call_fails(self):
        plain = "Fallback free-text sentiment."
        structured = MagicMock()
        structured.invoke.side_effect = ValueError("bad JSON from model")
        llm = MagicMock()
        llm.with_structured_output.return_value = structured
        llm.invoke.return_value = MagicMock(content=plain)
        assert create_sentiment_analyst(llm)(_make_sentiment_state())["sentiment_report"] == plain


@pytest.mark.unit
@pytest.mark.parametrize("source", [
    pytest.param(lambda: ResearchPlan.model_fields["recommendation"].description, id="ResearchPlan.recommendation"),
    pytest.param(lambda: PortfolioDecision.model_fields["rating"].description, id="PortfolioDecision.rating"),
    pytest.param(lambda: inspect.getsource(create_research_manager), id="research_manager prompt"),
    pytest.param(lambda: inspect.getsource(create_portfolio_manager), id="portfolio_manager prompt"),
])
def test_conflict_alone_is_not_a_hold_trigger(source):
    # The debate always contains conflicting arguments, so a Hold condition that
    # conflict satisfies fires on every run and swallows directional calls
    # (#1321). All four decision sites must state the same rule.
    # Task 9d (#83): 프롬프트가 한국어화되면서 Korean 등가 문구 "상충 자체는 Hold
    # 사유가 아닙니다" 도 수용. schema 필드 설명은 영어 유지 (파서/다운스트림 호환).
    text = " ".join(source().split())
    phrases = (
        "conflict alone is not a reason to Hold",
        "Conflicting arguments alone are not a reason to Hold",
        "상충 자체는 Hold 사유가 아닙니다",
    )
    assert any(p in text for p in phrases)
    assert "materially conflicting" not in text


@pytest.mark.unit
@pytest.mark.parametrize("written", ["150-160", "150 to 160", "around 150", "150/160", "~150"])
def test_a_price_written_as_a_range_drops_only_that_field(written):
    """Anything that is not a single number becomes None. Letting it through
    fails the whole decision's validation, and the run falls back to free text,
    losing every other field the model got right."""
    from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating

    decision = PortfolioDecision(rating=PortfolioRating.BUY, executive_summary="s",
                                 investment_thesis="t", price_target=written)
    assert decision.price_target is None


@pytest.mark.unit
def test_a_price_that_is_a_number_survives():
    from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating

    decision = PortfolioDecision(rating=PortfolioRating.BUY, executive_summary="s",
                                 investment_thesis="t", price_target="$1,150.25")
    assert decision.price_target == 1150.25


@pytest.mark.unit
def test_a_field_the_model_did_not_give_says_so():
    """An omitted line and a line never asked for read the same to an analyst."""
    from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating, render_pm_decision

    rendered = render_pm_decision(PortfolioDecision(
        rating=PortfolioRating.HOLD, executive_summary="s", investment_thesis="t"))
    # Task 9b (#81): Korean 디폴트 라벨 (목표가) + 안내 (제공되지 않음).
    assert "목표가" in rendered and "제공되지 않음" in rendered


@pytest.mark.unit
def test_the_trader_names_the_levels_it_did_not_give():
    from tradingagents.agents.schemas import TraderAction, TraderProposal, render_trader_proposal

    rendered = render_trader_proposal(TraderProposal(action=TraderAction.HOLD, reasoning="r"))
    for field in ("진입가", "손절가", "포지션 사이징"):
        assert field in rendered
    assert rendered.count("제공되지 않음") == 3


# ---- #145: 한국어 모드는 한국어 값, 영어 모드는 내부 값 그대로 ----

@pytest.fixture
def english_output(monkeypatch):
    from tradingagents.agents import schemas

    monkeypatch.setattr(schemas, "_output_language", lambda: "English")


@pytest.mark.unit
def test_english_mode_keeps_internal_values(english_output):
    plan = ResearchPlan(recommendation=PortfolioRating.UNDERWEIGHT, rationale="r", strategic_actions="a")
    assert "**Recommendation**: Underweight" in render_research_plan(plan)
    proposal = TraderProposal(action=TraderAction.SELL, reasoning="r")
    out = render_trader_proposal(proposal)
    assert "**Action**: Sell" in out
    assert "FINAL TRANSACTION PROPOSAL: **SELL**" in out
    report = SentimentReport(overall_band=SentimentBand.MIXED, overall_score=5.0,
                             confidence="medium", narrative="n")
    sr = render_sentiment_report(report)
    assert "**Overall Sentiment:** **Mixed**" in sr
    assert "**Confidence:** Medium" in sr


@pytest.mark.unit
def test_korean_rendered_lines_parse_back_to_internal_rating():
    from tradingagents.agents.rating import parse_rating
    from tradingagents.agents.schemas import render_pm_decision

    for rating in PortfolioRating:
        decision = PortfolioDecision(rating=rating, executive_summary="s", investment_thesis="t")
        assert parse_rating(render_pm_decision(decision)) == rating.value
    proposal = TraderProposal(action=TraderAction.BUY, reasoning="r")
    assert parse_rating(render_trader_proposal(proposal)) == "Buy"


# ---- #144: 시장 분석가는 차트 원본을 상태로 남긴다 ----

@pytest.mark.unit
def test_market_analyst_keeps_prefetched_data_for_report_charts():
    from unittest.mock import patch

    from tradingagents.agents.analysts import market_analyst

    prefetched = {"ohlcv": "o", "indicators": "i", "snapshot": "s", "investor_flow": "f"}
    with patch.object(market_analyst, "_prefetch_market_data", return_value=prefetched), \
         patch.object(market_analyst, "invoke_once", return_value=(MagicMock(), "리포트")):
        out = market_analyst.create_market_analyst(MagicMock())(
            {"company_of_interest": "034020", "trade_date": "2026-11-05", "messages": []}
        )
    assert out["market_report"] == "리포트"
    assert out["market_data"] == {"ohlcv": "o", "indicators": "i", "investor_flow": "f"}   # 스냅샷은 제외


@pytest.mark.unit
def test_news_analyst_keeps_each_macro_section_for_report_charts():
    from unittest.mock import patch

    from tradingagents.agents.analysts import news_analyst

    prefetched = {"ticker_news": "t", "global_news": "g", "macro": "m",
                  "macro_by_indicator": {"treasury_10y": "section"}}
    with patch.object(news_analyst, "_prefetch_news_data", return_value=prefetched), \
         patch.object(news_analyst, "invoke_once", return_value=(MagicMock(), "리포트")):
        out = news_analyst.create_news_analyst(MagicMock())(
            {"company_of_interest": "034020", "trade_date": "2026-11-05", "messages": []}
        )
    assert out["news_report"] == "리포트"
    assert out["macro_data"] == {"treasury_10y": "section"}
