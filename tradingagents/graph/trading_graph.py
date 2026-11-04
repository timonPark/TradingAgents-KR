import hashlib
import json
import logging
import os
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import tradingagents
from tradingagents.agents.context import build_instrument_context, resolve_instrument_identity
from tradingagents.agents.rating import run_rating
from tradingagents.dataflows.config import run_config, run_config_context, set_config
from tradingagents.dataflows.date_window import get_current_date, is_historical
from tradingagents.dataflows.symbols import safe_ticker_component
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients import create_tier_client
from tradingagents.memory import TradingMemoryLog, settlement
from tradingagents.memory.reflection import Reflector
from tradingagents.reporting import write_report_tree

from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .propagation import Propagator
from .setup import GraphSetup

logger = logging.getLogger(__name__)


def _validate_trade_date(trade_date) -> str:
    """The run date as a canonical ``YYYY-MM-DD`` string no later than today."""
    value = str(trade_date)
    try:
        canonical = datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") == value
    except ValueError:
        canonical = False
    if not canonical:
        raise ValueError(f"trade_date must be a date in YYYY-MM-DD format, got {trade_date!r}")
    if value > get_current_date():
        raise ValueError(f"trade_date cannot be in the future: {value}")
    return value


# Config keys that do not change what a run writes: where it keeps its files
# and whether it checkpoints. Task 2 (#21): llm_max_retries 는 제거됨 (어댑터가
# 자체 재시도 정책을 갖고 config 에 더 이상 노출되지 않음).
_NOT_IN_SIGNATURE = frozenset({
    "results_dir", "data_cache_dir", "memory_log_path", "checkpoint_enabled",
})

# Task 14e (#110): state 변화로 노드 완료를 감지하기 위한 라벨 매핑. 분석가
# 리포트와 토론/결정 단계 모두 한국어 라벨로 노출 (사용자 표시 전용).
_PROGRESS_LABELS: dict[str, str] = {
    "market_report": "시장 분석가",
    "sentiment_report": "감성 분석가",
    "news_report": "뉴스 분석가",
    "fundamentals_report": "재무 분석가",
    "investment_debate_state": "리서치 토론",
    "trader_investment_plan": "트레이더",
    "risk_debate_state": "리스크 토론",
    "final_trade_decision": "최종 결정",
}

# #126: LangGraph 의 node name → 사용자 라벨. state key 와 다르게 subgraph 안의
# bull/bear/aggressive/conservative/neutral 각각이 별도 호출로 보이도록 한다.
# 매칭 안 되는 키는 raw node name 을 그대로 쓴다 (UI 가 fallback 처리).
_NODE_LABELS: dict[str, str] = {
    # Top-level analyst subgraphs
    "Market Analyst": "시장 분석가",
    "Social Analyst": "감성 분석가",
    "News Analyst": "뉴스 분석가",
    "Fundamentals Analyst": "재무 분석가",
    # Analyst subgraph 내부 LLM 호출 노드 (공통 이름 "agent")
    "agent": "분석가 LLM",
    # Research debate
    "Bull Researcher": "강세 리서처",
    "Bear Researcher": "약세 리서처",
    "Research Manager": "리서치 매니저",
    # Trading / Risk / Portfolio
    "Trader": "트레이더",
    "Aggressive Risk Analyst": "공격적 리스크",
    "Conservative Risk Analyst": "보수적 리스크",
    "Neutral Risk Analyst": "중립적 리스크",
    "Risk Judge": "리스크 매니저",
    "Portfolio Manager": "포트폴리오 매니저",
    # Memory
    "Memory Log": "메모리 로그",
}


def _resolve_node_label(name: str | None) -> str:
    if not name:
        return "알 수 없는 노드"
    return _NODE_LABELS.get(name, name)


# #132: 토론 state (investment_debate_state 등) 안쪽의 사람이 읽을 만한 필드.
# 숫자/카운트 같은 메타 필드는 UI 노출 안 함.
_DEBATE_FIELD_LABELS: dict[str, str] = {
    "bull_history": "강세 논증",
    "bear_history": "약세 논증",
    "history": "토론 기록",
    "current_response": "최근 발언",
    "judge_decision": "매니저 판정",
    "aggressive_history": "공격적 리스크 관점",
    "conservative_history": "보수적 리스크 관점",
    "neutral_history": "중립적 리스크 관점",
    "current_aggressive_response": "공격적 리스크 최근 발언",
    "current_conservative_response": "보수적 리스크 최근 발언",
    "current_neutral_response": "중립적 리스크 최근 발언",
    "latest_speaker": "최근 발언자",
}


def _render_report_content(value) -> str:
    """노드 결과 state 를 사용자 표시용 마크다운으로 평탄화.

    - 문자열이면 그대로 (분석가 리포트, 트레이더 계획, 최종 결정 본문 등)
    - dict (debate_state 등) 면 알려진 필드만 소제목과 함께 마크다운으로 결합
    - 그 외는 빈 문자열 (UI 에 안 보임)
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts: list[str] = []
        for key, label in _DEBATE_FIELD_LABELS.items():
            v = value.get(key)
            if isinstance(v, str) and v.strip():
                parts.append(f"### {label}\n\n{v.strip()}")
        return "\n\n".join(parts)
    return ""


# Task 14e (#110) / #126: 진행 상황 콜백의 이벤트 dict 타입. 가능한 ``type`` 값:
#   - ``"run_start"``   : run 시작. ``ticker``, ``trade_date``.
#   - ``"node_start"``   : 노드 (subgraph 내부 agent 포함) 실행 시작. ``node``,
#                          ``label``, ``started_at``.
#   - ``"node_complete"``: 노드/분석가 완료. ``node``, ``label``,
#                          옵션 ``elapsed_ms``.
#   - ``"done"``        : run 완료. ``decision``.
#   - ``"error"``       : 예외. ``message``, ``traceback``.
ProgressEvent = dict[str, Any]
ProgressCallback = Callable[[ProgressEvent], None]


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=("market", "social", "news", "fundamentals"),
        debug=False,
        config: dict[str, Any] = None,
        callbacks: list | None = None,
        progress_callback: ProgressCallback | None = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
            progress_callback: Task 14e (#110) 로컬 웹 UI 가 노드 전환을 라이브로
                받기 위한 훅. 각 분석가/토론/결정 단계가 끝날 때마다 한 번씩,
                추가로 ``run_start`` / ``done`` / ``error`` 이벤트가 호출된다.
                예외는 삼키고 ``logger.warning`` 로만 노출 (분석 실행이
                UI 사정으로 중단되지 않도록).
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []
        self.progress_callback = progress_callback

        set_config(self.config)

        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        extra = {"callbacks": self.callbacks} if self.callbacks else {}
        self.deep_thinking_llm = create_tier_client(self.config, "deep", **extra).get_llm()
        self.quick_thinking_llm = create_tier_client(self.config, "quick", **extra).get_llm()

        self.memory_log = TradingMemoryLog(self.config)

        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        # Task 3 (#32): 모든 분석가가 사전조회 패턴으로 전환되어 ToolNode / tool
        # 루프 / `max_tool_rounds` 전부 제거됨 (ADR-0002). 분석가는 한 번의 LLM
        # 호출로 완결.
        max_recur_limit = self.config["max_recur_limit"]
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.conditional_logic,
        )

        self.propagator = Propagator(
            max_recur_limit=max_recur_limit,
        )
        self.reflector = Reflector(self.quick_thinking_llm)

        # Graph-shape-affecting run choices, kept for the checkpoint signature.
        self.selected_analysts = tuple(selected_analysts)

        # Set up the graph: keep the workflow for recompilation with a checkpointer.
        self.workflow = self.graph_setup.setup_graph(selected_analysts, memory_node=self._memory_step)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None
        self._resuming = False

    def resolve_instrument_context(self, ticker: str, asset_type: str = "stock",
                                   trade_date: str | None = None) -> str:
        """Resolve ticker identity once and return the full instrument context.

        Deterministic yfinance lookup (cached, fail-open) injected into a
        context string so every agent anchors to the real company instead of
        hallucinating one from the price chart (#814). Both the propagate()
        path and the CLI call this so the resolved identity reaches the whole
        graph regardless of entry point.
        """
        identity = resolve_instrument_identity(ticker)
        return build_instrument_context(ticker, asset_type, identity, trade_date)

    def _memory_as_of(self, trade_date) -> str | None:
        """Point-in-time cutoff for past-context lessons (#1251).

        A historical/backtest run (trade date before today) filters lessons to
        those already resolved by the trade date. A current-date run returns
        None, disabling the filter so live behavior and pre-migration entries
        (which have no stored resolution date) are unaffected.
        """
        return str(trade_date) if is_historical(trade_date) else None

    def _run_signature(self, asset_type: str, portfolio=None) -> str:
        """Run inputs that must invalidate a checkpoint if changed.

        Keyed into the checkpoint thread ID so a resume under a different analyst
        selection, debate/risk depth, or asset mode starts fresh instead of
        silently continuing the previous graph (#1089). The rest of the config
        counts too (provider, models, endpoint, language, vendors, limits): a
        resume must not carry reports that other settings produced. Only where
        the run keeps its files and how it retries are left out.
        """
        settings = {k: v for k, v in self.config.items() if k not in _NOT_IN_SIGNATURE}
        digest = hashlib.sha256(json.dumps(settings, sort_keys=True, default=str).encode()).hexdigest()[:12]
        return "|".join([
            "analysts=" + ",".join(self.selected_analysts),
            f"debate={self.config['max_debate_rounds']}",
            f"risk={self.config['max_risk_discuss_rounds']}",
            f"asset={asset_type}",
            # None, an empty book and a changed book are three different runs.
            f"portfolio={portfolio.fingerprint() if portfolio is not None else 'none'}",
            # The layout itself: a checkpoint saved when analysts ran one after
            # another has pending nodes this graph no longer has, and one saved
            # before the Memory Log step would resume without the lessons.
            "analysts=parallel",
            "memory=parallel",
            f"settings={digest}",
        ])

    def propagate(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        """Run the trading agents graph for a company on a specific date.

        ``asset_type`` selects between the stock pipeline (default) and the
        crypto pipeline (``"crypto"``) shipped in #567 — the CLI auto-detects
        from the ticker; programmatic callers pass it explicitly. When
        ``checkpoint_enabled`` is set in config, the graph is recompiled with
        a per-ticker SqliteSaver so a crashed run can resume from the last
        successful node on a subsequent invocation with the same ticker+date.

        Returns ``(final_state, signal)`` where ``signal`` is one of the 5-tier
        ratings (Buy / Overweight / Hold / Underweight / Sell) or ``"REVIEW"``
        when the decision had no parseable rating (#1170); guard with
        ``tradingagents.agents.rating.is_review`` before mapping it to the
        PortfolioRating enum.
        """
        trade_date = _validate_trade_date(trade_date)

        with run_config(self.config), \
                self.checkpoint_scope(company_name, trade_date, asset_type, portfolio) as thread_id_value:
            return self._run_graph(
                company_name, trade_date, asset_type=asset_type,
                checkpoint_thread_id=thread_id_value, portfolio=portfolio,
            )

    def begin_checkpoint(self, company_name, trade_date, asset_type: str = "stock", portfolio=None) -> str | None:
        """Recompile the graph with a per-ticker checkpointer and return the
        ``thread_id`` to inject into the stream/invoke ``config`` (or ``None``
        when checkpointing is disabled).

        Pair every call with :meth:`end_checkpoint` in a ``finally``. Both
        ``propagate`` (via :meth:`checkpoint_scope`) and the CLI stream path use
        this so ``--checkpoint`` actually resumes (#1249); previously the setup
        lived only inside ``propagate`` and the CLI streamed the checkpointer-less
        graph, making the flag a no-op.
        """
        self._resuming = False
        if not self.config.get("checkpoint_enabled"):
            return None
        signature = self._run_signature(asset_type, portfolio)
        self._checkpointer_ctx = get_checkpointer(self.config["data_cache_dir"], company_name)
        saver = self._checkpointer_ctx.__enter__()
        self.graph = self.workflow.compile(checkpointer=saver)

        step = checkpoint_step(
            self.config["data_cache_dir"], company_name, str(trade_date), signature
        )
        self._resuming = step is not None
        if step is not None:
            logger.info("Resuming from step %d for %s on %s", step, company_name, trade_date)
        else:
            logger.info("Starting fresh for %s on %s", company_name, trade_date)
        return thread_id(company_name, str(trade_date), signature)

    def checkpoint_input(self, init_state):
        """The value to stream/invoke: ``None`` to resume an existing checkpoint,
        else the initial state for a fresh run.

        LangGraph resumes an interrupted thread when invoked with ``None``;
        re-passing the initial state instead appends it through the message
        reducer, duplicating messages in the resumed state (#1249).
        """
        return None if self._resuming else init_state

    def end_checkpoint(self):
        """Restore the plain uncheckpointed graph after a checkpointed run."""
        if self._checkpointer_ctx is not None:
            self._checkpointer_ctx.__exit__(None, None, None)
            self._checkpointer_ctx = None
            self.graph = self.workflow.compile()
        self._resuming = False

    @contextmanager
    def checkpoint_scope(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        """Context-manager form of begin/end_checkpoint for the propagate path."""
        try:
            yield self.begin_checkpoint(company_name, trade_date, asset_type, portfolio)
        finally:
            self.end_checkpoint()

    def clear_checkpoint_on_success(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        """Drop a completed run's checkpoint so a later run starts fresh (#1249)."""
        if self.config.get("checkpoint_enabled"):
            clear_checkpoint(
                self.config["data_cache_dir"], company_name, str(trade_date),
                self._run_signature(asset_type, portfolio),
            )

    def run_settings(self) -> dict:
        """What produces this graph's runs, for the saved report and state log.

        An allowlist: keys and local paths are never recorded. Task 2 (#21) 로
        provider-specific 설정(backend_url, deep_think_provider, quick_think_
        provider 등) 은 제거되었습니다 — provider 가 claude-code 로 고정이므로.
        """
        cfg = self.config
        return {
            "version": tradingagents.__version__,
            "llm_provider": cfg.get("llm_provider"),
            "deep_think_llm": cfg.get("deep_think_llm"),
            "quick_think_llm": cfg.get("quick_think_llm"),
            "effort": cfg.get("effort"),
            "quick_effort": cfg.get("quick_effort"),
            "analysts": list(self.selected_analysts),
            "max_debate_rounds": cfg.get("max_debate_rounds"),
            "max_risk_discuss_rounds": cfg.get("max_risk_discuss_rounds"),
            "output_language": cfg.get("output_language"),
            "data_vendors": dict(cfg.get("data_vendors") or {}),
            "tool_vendors": dict(cfg.get("tool_vendors") or {}),
        }

    def save_reports(self, final_state, ticker, save_path=None, html=True) -> Path:
        """Write the report tree for a completed run, like the CLI does.

        Programmatic callers get the same on-disk reports the CLI produces. Pass
        an explicit ``save_path`` or let it default under ``results_dir``; the
        report is also written as one HTML page unless ``html`` is False.
        """
        if save_path is None:
            save_path = self.default_report_path(ticker)
        return write_report_tree(final_state, ticker, save_path, settings=self.run_settings(), html=html)

    def default_report_path(self, ticker) -> Path:
        """Where a run's reports go unless told otherwise: under results_dir, stamped now."""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return Path(self.config["results_dir"]) / "reports" / f"{safe_ticker_component(ticker)}_{stamp}"

    def create_run_state(self, company_name, trade_date, asset_type: str = "stock", portfolio=None):
        """Build a run's initial state; propagate() and the CLI both start here.

        Injects the resolved instrument identity for every agent (#814). The
        memory log's lessons are not here: the graph's Memory Log step settles
        and loads them alongside the analysts (see ``_memory_step``).
        """
        trade_date = _validate_trade_date(trade_date)
        return self.propagator.create_initial_state(
            company_name,
            trade_date,
            asset_type=asset_type,
            instrument_context=self.resolve_instrument_context(company_name, asset_type, trade_date),
            portfolio_context=portfolio.render(company_name) if portfolio is not None else "",
        )

    def _memory_step(self, state):
        """The graph's Memory Log step, alongside the analysts (#1428): settle every
        ticker's due decisions (#1445), then return the lessons known by the
        trade date for the Portfolio Manager (#1251).

        Settling fetches prices and asks the model for a reflection per decision,
        so it runs beside the analysts instead of before them. A failure here
        does not end the run: the analysts' work is kept, the lessons already in
        the log are used, and the report says what could not be settled.
        """
        note = ""
        try:
            # Another run settling the same log does the work; this one goes on.
            done = self.settle_all_pending(wait=False)
            if done.failed:
                note = (f"{len(done.failed)} past decision(s) could not be settled this run "
                        "and stay pending.")
        except Exception as exc:
            logger.warning("Settling past decisions failed: %s", exc)
            note = f"Past decisions could not be settled this run ({type(exc).__name__}); they stay pending."
        try:
            past_context = self.memory_log.get_past_context(
                state["company_of_interest"], as_of=self._memory_as_of(state["trade_date"]))
        except Exception as exc:
            logger.warning("Reading the memory log failed: %s", exc)
            past_context = ""
            note = note or f"The memory log could not be read this run ({type(exc).__name__})."
        return {"past_context": past_context, "memory_note": note}

    def settle_pending(self, company_name) -> settlement.Settlement:
        """Settle this ticker's decisions whose holding window has now traded.

        A run settles every due decision alongside its analysts, so its own
        decision stays pending until a later run. A caller that is done
        analyzing a ticker (a backtest sweep, a scheduled job) calls this to
        settle it now. Returns what was settled and what failed.
        """
        with run_config(self.config):
            return settlement.settle_pending(company_name, self.memory_log, self.reflector, self.config)

    def settle_all_pending(self, wait: bool = True) -> settlement.Settlement:
        """Settle every ticker's decisions whose holding window has now traded (#1445).

        For a scheduler whose tickers rotate: a ticker it stops analysing would
        otherwise keep its decisions pending, and their lessons out of later runs.
        With ``wait=False`` a pass already running on the same log is not waited for.
        """
        with run_config(self.config):
            return settlement.settle_all_pending(self.memory_log, self.reflector, self.config, wait=wait)

    def record_decision(self, company_name, trade_date, final_state):
        """Record a finished run: its state log, and its decision in the memory log
        for reflection on the next same-ticker run. propagate() and the CLI both end here."""
        self._log_state(trade_date, final_state)
        decision = final_state.get("final_trade_decision")
        if not decision:
            logger.warning("No final decision for %s on %s; nothing added to the memory log",
                           company_name, trade_date)
            return
        self.memory_log.store_decision(
            ticker=company_name, trade_date=trade_date, final_trade_decision=decision,
            rating=run_rating(final_state),
        )

    def _run_graph(self, company_name, trade_date, asset_type: str = "stock",
                   checkpoint_thread_id: str | None = None, portfolio=None):
        """Execute the graph and write the resulting state to disk and memory log."""
        init_agent_state = self.create_run_state(company_name, trade_date, asset_type, portfolio)
        args = self.propagator.get_graph_args()

        # Inject the checkpoint thread_id (from checkpoint_scope) so the same
        # ticker+date+graph-shape resumes; a different one starts fresh (#1089).
        if checkpoint_thread_id is not None:
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = checkpoint_thread_id

        # None resumes an existing checkpoint; init_agent_state starts fresh (#1249).
        graph_input = self.checkpoint_input(init_agent_state)
        self._emit_progress({"type": "run_start", "ticker": company_name, "trade_date": str(trade_date)})
        # Task 14e (#110): debug 모드에선 stream_run 으로 pretty_print 하며 state
        # diff 로 node_complete 도 함께 emit. 비-debug 경로는 종전과 동일하게
        # graph.invoke 한 번으로 끝 — 그 경우 노드 전환은 알 수 없고 run_start /
        # done 이벤트만 발화 (로컬 웹 UI 가 "노드별 라이브" 를 원하면 debug=True
        # 로 생성하도록 안내).
        #
        # #126: debug=True 경로에서 추가로 subgraph task 의 시작/종료를 받아
        # 활성 agent (예: Bull/Bear/Trader) 를 node_start / node_complete 로
        # emit 한다. 라운드 반복이나 agent 호출 대기 시간을 외부에서 관측 가능.
        if self.debug:
            # A state repeats the messages before it, so each prints once (#1027).
            final_state, printed = {}, set()
            seen_state_nodes: set[str] = set()
            for event in self._iter_graph_events(graph_input, **args):
                kind = event["kind"]
                if kind == "message":
                    for msg in event["messages"]:
                        key = (
                            getattr(msg, "id", None)
                            or (type(msg).__name__, getattr(msg, "content", None))
                        )
                        if key not in printed:
                            printed.add(key)
                            msg.pretty_print()
                elif kind == "task_start":
                    self._emit_progress({
                        "type": "node_start",
                        "node": event["name"],
                        "label": _resolve_node_label(event["name"]),
                        "started_at": event["started_at"],
                    })
                elif kind == "task_complete":
                    self._emit_progress({
                        "type": "node_complete",
                        "node": event["name"],
                        "label": _resolve_node_label(event["name"]),
                        "elapsed_ms": event.get("elapsed_ms"),
                    })
                elif kind == "state_update":
                    state = event["state"]
                    final_state.update(state)
                    # top-level state 키 기반 보조 emit — 기존 UI 와 호환.
                    # task 이벤트가 뜨지 않더라도 완료는 반드시 보이도록.
                    for node_key, label in _PROGRESS_LABELS.items():
                        if node_key in seen_state_nodes:
                            continue
                        value = final_state.get(node_key)
                        if value:
                            seen_state_nodes.add(node_key)
                            # #132: 노드가 끝나면 그 분석가/리서처의 **리포트 본문**
                            # 을 함께 보내 UI 가 즉시 렌더링할 수 있게 한다. 사용자가
                            # 중간 결과를 못 보고 수십 분 기다리던 문제의 해소.
                            self._emit_progress({
                                "type": "node_complete",
                                "node": node_key,
                                "label": label,
                                "content": _render_report_content(value),
                            })
        else:
            final_state = self.graph.invoke(graph_input, **args)

        self.record_decision(company_name, trade_date, final_state)

        # Clear checkpoint on successful completion to avoid stale state.
        self.clear_checkpoint_on_success(company_name, trade_date, asset_type, portfolio)

        rating = run_rating(final_state)
        self._emit_progress({"type": "done", "decision": rating})
        return final_state, rating

    def _emit_progress(self, event: ProgressEvent) -> None:
        """Task 14e (#110): 진행 콜백을 안전하게 호출.

        - ``__init__`` 을 우회해 생성된 테스트 더블 (``object.__new__``) 도
          허용 — ``getattr`` 로 기본값 ``None``.
        - 콜백 예외는 삼키고 ``logger.warning`` 으로만 노출 — UI 사정으로
          분석 파이프라인이 중단되지 않도록 한다.
        """
        cb = getattr(self, "progress_callback", None)
        if cb is None or not callable(cb):
            return
        try:
            cb(event)
        except Exception as exc:  # noqa: BLE001 — 콜백 격리가 요점
            logger.warning("progress_callback raised: %s", exc)

    def _iter_graph_events(self, graph_input, **args):
        """#126: LangGraph stream 을 **task 시작 / 완료 / state / messages** 로
        정규화해 yield 한다.

        ``stream_mode=["values","tasks"]`` + ``subgraphs=True`` 로 돌면 subgraph
        안의 bull/bear/trader/aggressive/conservative/neutral 각 호출이 "tasks"
        모드 chunk 로 들어온다. 같은 task 는 **시작 시 result=None, 완료 시
        result=<dict>** 두 번 등장하므로 그걸로 start/complete 구분.

        yield shape:
        - ``{"kind": "task_start", "name": str, "started_at": ISO8601}``
        - ``{"kind": "task_complete", "name": str, "elapsed_ms": int | None}``
        - ``{"kind": "state_update", "state": dict}``   — top-level values
        - ``{"kind": "message", "messages": list}``     — top-level messages
        """
        args = {**args, "stream_mode": ["values", "tasks"]}
        context = run_config_context(self.config)
        stream = context.run(self.graph.stream, graph_input, subgraphs=True, **args)

        # 같은 task 가 두 번 보이므로 처음 등장 시각을 기록.
        task_started: dict[str, datetime] = {}

        try:
            while (step := context.run(next, stream, None)) is not None:
                namespace, mode, chunk = step

                if mode == "tasks" and isinstance(chunk, dict):
                    name = chunk.get("name")
                    if not name:
                        continue
                    result = chunk.get("result")
                    # 같은 task 이름이 여러 번 호출될 수 있음 (라운드 반복). task
                    # ID 가 있으면 그걸 우선, 없으면 name 기반.
                    task_id = str(chunk.get("id") or name)
                    if result is None:
                        # task 시작
                        now = datetime.now(UTC)
                        task_started[task_id] = now
                        yield {
                            "kind": "task_start",
                            "name": name,
                            "started_at": now.isoformat(),
                        }
                    else:
                        started = task_started.pop(task_id, None)
                        elapsed_ms = None
                        if started is not None:
                            elapsed_ms = int(
                                (datetime.now(UTC) - started).total_seconds() * 1000
                            )
                        yield {
                            "kind": "task_complete",
                            "name": name,
                            "elapsed_ms": elapsed_ms,
                        }
                        # tasks 모드의 result 도 하위 state/message 참고용으로
                        # 반환 — 기존 stream_run 과 호환 위해.
                        if isinstance(result, dict):
                            report = {
                                k: v for k, v in result.items()
                                if k != "messages" and v
                            }
                            if result.get("messages"):
                                yield {
                                    "kind": "message",
                                    "messages": result.get("messages", []),
                                }
                            if report:
                                yield {"kind": "state_update", "state": report}

                elif mode == "values" and not namespace:
                    # top-level graph state. messages 와 state 각각 분리 emit.
                    if chunk.get("messages"):
                        yield {
                            "kind": "message",
                            "messages": chunk.get("messages", []),
                        }
                    yield {"kind": "state_update", "state": chunk}
        finally:
            context.run(stream.close)

    def stream_run(self, graph_input, **args):
        """Stream a run as ``(messages, state)`` pairs.

        ``messages`` are the agents' messages, the analysts' included. ``state``
        is the run's state after a top-level step; for a step inside an analyst's
        graph it is that analyst's report once filed, else None.

        Each analyst works in a graph of its own, and the run's state takes the
        analysts' reports only when the slowest has finished, so their messages
        and reports come from their own finished steps ("tasks") as they happen.
        """
        args = {**args, "stream_mode": ["values", "tasks"]}
        # The graph's own config serves every tool call, as in propagate(), even
        # when the process-wide config has changed since. Each step runs in the
        # run's context, so the caller keeps its own between steps.
        context = run_config_context(self.config)
        stream = context.run(self.graph.stream, graph_input, subgraphs=True, **args)
        try:
            while (step := context.run(next, stream, None)) is not None:
                namespace, mode, chunk = step
                if namespace:
                    result = chunk.get("result") if mode == "tasks" else None
                    if isinstance(result, dict):
                        report = {k: v for k, v in result.items() if k != "messages" and v}
                        if result.get("messages") or report:
                            yield result.get("messages", []), report or None
                elif mode == "values":
                    yield chunk.get("messages", []), chunk
        finally:
            context.run(stream.close)

    def _log_state(self, trade_date, final_state):
        """Write a run's final state to JSON under the run's own ticker."""
        entry = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
            },
            "trader_investment_plan": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
            "final_rating": run_rating(final_state),
            "run_settings": self.run_settings(),
        }

        # A ticker that would escape the results directory is rejected.
        safe_ticker = safe_ticker_component(final_state["company_of_interest"])
        directory = Path(self.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            # Reports can be in any language and this file is read by a person.
            json.dump(entry, f, indent=4, ensure_ascii=False)
