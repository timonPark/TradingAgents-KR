/**
 * Task 14e (#110) — 종목 검색부터 분석 시작, 라이브 진행, 완료까지
 * 한 화면에 묶는 React 아일랜드.
 *
 * - 상단: SymbolSearch (14d) 결과를 받아 선택된 종목을 보관
 * - 중단: 분석 날짜 / 분석가 체크박스 / 모델·effort 선택
 * - 하단: "분석 시작" → POST /api/runs → SSE 구독 → 노드 전환을
 *         chrono 스타일로 렌더
 */

import { useEffect, useRef, useState } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import ReportFrame from "./ReportFrame";
import SymbolSearch, { type SymbolHit } from "./SymbolSearch";
import "./RunPanel.css";
import { ratingLabel } from "../utils/rating";

const API_BASE =
	(import.meta.env.PUBLIC_API_BASE as string | undefined) ??
	"http://localhost:8000";

type AnalystKey = "market" | "social" | "news" | "fundamentals";

const ANALYST_OPTIONS: { key: AnalystKey; label: string }[] = [
	{ key: "market", label: "시장" },
	{ key: "social", label: "감성" },
	{ key: "news", label: "뉴스" },
	{ key: "fundamentals", label: "재무" },
];

const MODEL_OPTIONS = ["sonnet", "opus", "haiku"] as const;
const EFFORT_OPTIONS = ["low", "medium", "high", "xhigh", "max"] as const;

type Model = (typeof MODEL_OPTIONS)[number];
type Effort = (typeof EFFORT_OPTIONS)[number];

interface Event {
	type: string;
	label?: string;
	node?: string;
	decision?: string;
	message?: string;
	started_at?: string;
	elapsed_ms?: number;
	content?: string;
	report_id?: string;
	ticker?: string;
	trade_date?: string;
}

function renderMarkdown(src: string): string {
	return DOMPurify.sanitize(marked.parse(src, { async: false }) as string);
}

function todayKst(): string {
	const now = new Date();
	// 로케일 중립적인 KST 환산: UTC + 9 시간.
	const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
	return kst.toISOString().slice(0, 10);
}

/** 초를 "7분 15초" 형식으로. */
function formatElapsed(seconds: number): string {
	if (seconds < 60) return `${seconds}초`;
	const m = Math.floor(seconds / 60);
	const s = seconds % 60;
	return s > 0 ? `${m}분 ${s}초` : `${m}분`;
}

export default function RunPanel() {
	const [selected, setSelected] = useState<SymbolHit | null>(null);
	const [tradeDate, setTradeDate] = useState(todayKst());
	const [analysts, setAnalysts] = useState<Set<AnalystKey>>(
		new Set<AnalystKey>(["market", "social", "news", "fundamentals"]),
	);
	const [deepModel, setDeepModel] = useState<Model>("sonnet");
	const [quickModel, setQuickModel] = useState<Model>("haiku");
	const [effort, setEffort] = useState<Effort>("low");

	const [runId, setRunId] = useState<string | null>(null);
	const [events, setEvents] = useState<Event[]>([]);
	const [status, setStatus] = useState<"idle" | "starting" | "running" | "done" | "error">(
		"idle",
	);
	const [errorMsg, setErrorMsg] = useState<string | null>(null);
	const sourceRef = useRef<EventSource | null>(null);

	useEffect(() => {
		const existingRun = new URLSearchParams(window.location.search).get("run");
		if (existingRun) {
			setRunId(existingRun);
			setStatus("running");
			openStream(existingRun);
		}
		return () => {
			sourceRef.current?.close();
		};
	}, []);

	function toggleAnalyst(key: AnalystKey) {
		setAnalysts((prev) => {
			const next = new Set(prev);
			if (next.has(key)) next.delete(key);
			else next.add(key);
			return next;
		});
	}

	async function start() {
		if (!selected) return;
		setStatus("starting");
		setEvents([]);
		setErrorMsg(null);
		try {
			const response = await fetch(`${API_BASE}/api/runs`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					ticker: selected.ticker,
					trade_date: tradeDate,
					analysts: Array.from(analysts),
					deep_think_llm: deepModel,
					quick_think_llm: quickModel,
					effort,
				}),
			});
			if (!response.ok) throw new Error(`POST /api/runs → ${response.status}`);
			const { run_id } = (await response.json()) as { run_id: string };
			setRunId(run_id);
			const url = new URL(window.location.href);
			url.searchParams.set("run", run_id);
			window.history.replaceState(null, "", url);
			setStatus("running");
			openStream(run_id);
		} catch (err) {
			setErrorMsg(err instanceof Error ? err.message : String(err));
			setStatus("error");
		}
	}

	function openStream(id: string) {
		sourceRef.current?.close();
		setEvents([]);
		const source = new EventSource(`${API_BASE}/api/runs/${id}/events`);
		sourceRef.current = source;

		let finished = false;
		const handleEvent = (event: Event) => {
			if (sourceRef.current !== source) return;
			setEvents((prev) => [...prev, event]);
			if (event.type === "done") {
				setStatus("done");
				finished = true;
				source.close();
			} else if (event.type === "error") {
				setErrorMsg(event.message ?? "알 수 없는 에러");
				setStatus("error");
				source.close();
			}
		};

		for (const type of ["run_start", "node_start", "node_complete", "report_saved", "done", "error"]) {
			source.addEventListener(type, (raw) => {
				try {
					const data = JSON.parse((raw as MessageEvent).data) as Event;
					handleEvent(data);
				} catch (err) {
					console.error("이벤트 파싱 실패", err);
				}
			});
		}

		source.onerror = () => {
			if (finished) return;
			setErrorMsg("SSE 연결 끊김 — uvicorn 이 켜져 있는지 확인하세요.");
			setStatus("error");
			source.close();
		};
	}

	const nodeEvents = events.filter((e) => e.type === "node_complete");
	const startEvent = events.find((e) => e.type === "run_start");
	const savedEvent = events.find((e) => e.type === "report_saved");
	const doneEvent = events.find((e) => e.type === "done");

	// Parallel analysts remain active until their own completion arrives.
	const activeEvents = (() => {
		const active = new Map<string, Event>();
		for (const event of events) {
			if (event.type === "node_start" && event.node) active.set(event.node, event);
			if (event.type === "node_complete" && event.node) active.delete(event.node);
			if (event.type === "done" || event.type === "error") active.clear();
		}
		return Array.from(active.values());
	})();
	const activeEvent = activeEvents[0];

	// 지금 활성 노드의 경과 시간을 1초 간격으로 리렌더링.
	const [, forceTick] = useState(0);
	useEffect(() => {
		if (!activeEvent) return;
		const timer = window.setInterval(() => forceTick((n) => n + 1), 1000);
		return () => window.clearInterval(timer);
	}, [activeEvent?.started_at]);

	const activeElapsedSeconds = (() => {
		if (!activeEvent?.started_at) return null;
		const start = new Date(activeEvent.started_at).getTime();
		if (Number.isNaN(start)) return null;
		return Math.max(0, Math.floor((Date.now() - start) / 1000));
	})();

	const disableStart =
		!selected ||
		analysts.size === 0 ||
		status === "starting" ||
		status === "running";

	return (
		<div className="run-panel">
			<SymbolSearch onSelect={setSelected} />

			<fieldset className="run-settings" disabled={status === "running" || status === "starting"}>
				<legend className="settings-legend">분석 설정</legend>

				<div className="settings-row">
					<label htmlFor="trade-date" className="settings-label">
						분석 날짜
					</label>
					<input
						id="trade-date"
						type="date"
						className="settings-input"
						value={tradeDate}
						onChange={(e) => setTradeDate(e.target.value)}
					/>
				</div>

				<div className="settings-row">
					<span className="settings-label">분석가</span>
					<div className="checkbox-row">
						{ANALYST_OPTIONS.map((opt) => (
							<label key={opt.key} className="checkbox">
								<input
									type="checkbox"
									checked={analysts.has(opt.key)}
									onChange={() => toggleAnalyst(opt.key)}
								/>
								<span>{opt.label}</span>
							</label>
						))}
					</div>
				</div>

				<div className="settings-row">
					<label htmlFor="deep-model" className="settings-label">
						심층 모델
					</label>
					<select
						id="deep-model"
						className="settings-input"
						value={deepModel}
						onChange={(e) => setDeepModel(e.target.value as Model)}
					>
						{MODEL_OPTIONS.map((m) => (
							<option key={m} value={m}>
								{m}
							</option>
						))}
					</select>
					<label htmlFor="quick-model" className="settings-label">
						간이 모델
					</label>
					<select
						id="quick-model"
						className="settings-input"
						value={quickModel}
						onChange={(e) => setQuickModel(e.target.value as Model)}
					>
						{MODEL_OPTIONS.map((m) => (
							<option key={m} value={m}>
								{m}
							</option>
						))}
					</select>
				</div>

				<div className="settings-row">
					<label htmlFor="effort" className="settings-label">
						Effort
					</label>
					<select
						id="effort"
						className="settings-input"
						value={effort}
						onChange={(e) => setEffort(e.target.value as Effort)}
					>
						{EFFORT_OPTIONS.map((x) => (
							<option key={x} value={x}>
								{x}
							</option>
						))}
					</select>
				</div>
			</fieldset>

			<div className="ks-button-row run-actions">
				<button
					type="button"
					className="ks-button ks-button-primary"
					disabled={disableStart}
					onClick={start}
				>
					{status === "running" || status === "starting"
						? "분석 중…"
						: "분석 시작"}
				</button>
				{selected && (
					<span className="chosen">
						선택 · <strong>{selected.ticker}</strong> {selected.name}
					</span>
				)}
			</div>

			{(status === "running" || status === "done" || status === "error") && (
				<section className="run-live" aria-live="polite">
					<h3 className="live-head">진행 상황</h3>
					{startEvent && <p>{startEvent.ticker} · 분석일 {startEvent.trade_date}</p>}

					{/* #126: 활성 노드 패널 — 지금 돌고 있는 agent 와 경과 시간 */}
					{activeEvent && (
						<div className="live-active">
							<span className="active-dot" aria-hidden="true" />
							<div className="active-body">
								<span className="active-label">
									{activeEvents.map((event) => event.label ?? event.node).join(" · ")}
								</span>
								<span className="active-meta">
									{activeElapsedSeconds != null
										? `응답 대기 중 · ${formatElapsed(activeElapsedSeconds)}`
										: "응답 대기 중"}
								</span>
							</div>
						</div>
					)}

					<ol className="live-steps">
						{nodeEvents.map((event, i) => (
							<li key={`${event.node}-${i}`} className="live-step is-done">
								<div className="step-head">
									<span className="step-dot" aria-hidden="true" />
									<span className="step-label">
										{event.label ?? event.node}
										{typeof event.elapsed_ms === "number" && (
											<span className="step-elapsed">
												{" · "}
												{formatElapsed(Math.round(event.elapsed_ms / 1000))}
											</span>
										)}
									</span>
								</div>
								{event.content && event.content.trim().length > 0 && (
									<details className="step-report" open>
										<summary>분석 결과 보기</summary>
										<div
											className="step-report-body"
											dangerouslySetInnerHTML={{
												__html: renderMarkdown(event.content),
											}}
										/>
									</details>
								)}
							</li>
						))}
						{status === "running" && !activeEvent && (
							<li className="live-step is-live">
								<span className="step-dot" aria-hidden="true" />
								<span className="step-label">진행 중…</span>
							</li>
						)}
					</ol>

					{doneEvent && (
						<p className="live-decision">
							결정: <strong>{ratingLabel(doneEvent.decision)}</strong>
						</p>
					)}

					{savedEvent?.report_id && (
						<div className="ks-button-row">
							{(["md", "html", "pdf"] as const).map((format) => (
								<a key={format} className="ks-button" href={`${API_BASE}/api/reports/${encodeURIComponent(savedEvent.report_id!)}/download?format=${format}`}>
									{format.toUpperCase()} 다운로드
								</a>
							))}
							<a className="ks-button" href={`/report?id=${encodeURIComponent(savedEvent.report_id)}`}>리포트 뷰어로 이동</a>
						</div>
					)}

					{savedEvent?.report_id && <ReportFrame reportId={savedEvent.report_id} />}

					{errorMsg && <p className="live-error">에러: {errorMsg}</p>}

					{runId && (
						<p className="live-meta">
							run_id: <code>{runId}</code>
						</p>
					)}
				</section>
			)}
		</div>
	);
}
