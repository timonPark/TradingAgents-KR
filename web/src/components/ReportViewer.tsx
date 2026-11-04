/**
 * Task 14f (#111) — 과거 리포트 사이드바 + 마크다운 뷰어.
 *
 * - 사이드바: `GET /api/reports` 최근 50개, 결정 배지 포함
 * - 메인: `GET /api/reports/{id}` 의 파일 목록을 섹션 탭으로 묶어 표시
 * - 마크다운은 `marked` + `DOMPurify` 로 렌더 (런타임 sanitize)
 */

import { useEffect, useMemo, useState } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import "./ReportViewer.css";

const API_BASE =
	(import.meta.env.PUBLIC_API_BASE as string | undefined) ??
	"http://localhost:8000";

interface Summary {
	report_id: string;
	ticker: string;
	name: string | null;
	stamp: string;
	decision: string | null;
}

interface ReportFile {
	path: string;
	content: string;
}

interface Tree {
	report_id: string;
	ticker: string;
	name: string | null;
	stamp: string;
	decision: string | null;
	files: ReportFile[];
}

/** 섹션 라벨 — kinpaku 디자인 가드. */
const SECTION_LABELS: Record<string, string> = {
	complete: "전체",
	analysts: "분석가",
	research: "리서치",
	trading: "트레이더",
	risk: "리스크",
	portfolio: "포트폴리오",
};

function sectionOf(path: string): string {
	if (path === "complete_report.md") return "complete";
	const [folder] = path.split("/");
	return folder;
}

function decisionClass(decision: string | null): string {
	if (!decision) return "is-neutral";
	const lower = decision.toLowerCase();
	if (lower.startsWith("buy") || lower.startsWith("overweight")) return "is-buy";
	if (lower.startsWith("sell") || lower.startsWith("underweight")) return "is-sell";
	return "is-neutral";
}

export default function ReportViewer() {
	const [summaries, setSummaries] = useState<Summary[]>([]);
	const [selected, setSelected] = useState<string | null>(null);
	const [tree, setTree] = useState<Tree | null>(null);
	const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
	const [activeSection, setActiveSection] = useState<string>("complete");

	useEffect(() => {
		fetch(`${API_BASE}/api/reports?limit=50`)
			.then((r) => r.json() as Promise<Summary[]>)
			.then((items) => {
				setSummaries(items);
				// URL 쿼리에서 id 파라미터 → 초기 선택
				const params = new URLSearchParams(window.location.search);
				const idFromUrl = params.get("id");
				if (idFromUrl) {
					setSelected(idFromUrl);
				} else if (items.length) {
					setSelected(items[0].report_id);
				}
			})
			.catch(() => setStatus("error"));
	}, []);

	useEffect(() => {
		if (!selected) return;
		setStatus("loading");
		setTree(null);
		setActiveSection("complete");
		fetch(`${API_BASE}/api/reports/${encodeURIComponent(selected)}`)
			.then((r) => {
				if (!r.ok) throw new Error(String(r.status));
				return r.json() as Promise<Tree>;
			})
			.then((data) => {
				setTree(data);
				setStatus("idle");
				// URL 동기화
				const params = new URLSearchParams(window.location.search);
				params.set("id", data.report_id);
				window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
			})
			.catch(() => setStatus("error"));
	}, [selected]);

	const filesBySection = useMemo(() => {
		if (!tree) return {} as Record<string, ReportFile[]>;
		const buckets: Record<string, ReportFile[]> = {};
		for (const file of tree.files) {
			const section = sectionOf(file.path);
			(buckets[section] ||= []).push(file);
		}
		return buckets;
	}, [tree]);

	const sectionOrder = useMemo(() => {
		const known = Object.keys(SECTION_LABELS);
		return known.filter((s) => filesBySection[s]?.length);
	}, [filesBySection]);

	useEffect(() => {
		if (!sectionOrder.includes(activeSection) && sectionOrder.length) {
			setActiveSection(sectionOrder[0]);
		}
	}, [sectionOrder, activeSection]);

	return (
		<div className="report-viewer">
			<aside className="report-sidebar">
				<h2 className="sidebar-head">과거 분석</h2>
				{summaries.length === 0 && (
					<p className="sidebar-empty">
						저장된 리포트가 없습니다. 홈에서 분석을 실행하면 여기 쌓입니다.
					</p>
				)}
				<ul className="sidebar-list">
					{summaries.map((s) => (
						<li
							key={s.report_id}
							className={`sidebar-row ${s.report_id === selected ? "is-active" : ""}`}
							onClick={() => setSelected(s.report_id)}
						>
							<span className="row-stamp">{s.stamp.slice(0, 16).replace("T", " ")}</span>
							<span className="row-ticker">
								{s.ticker}
								{s.name ? ` · ${s.name}` : ""}
							</span>
							{s.decision && (
								<span className={`ks-tag ${decisionClass(s.decision)}`}>{s.decision}</span>
							)}
						</li>
					))}
				</ul>
			</aside>

			<section className="report-main">
				{status === "loading" && <p className="report-status">불러오는 중…</p>}
				{status === "error" && (
					<p className="report-status is-error">
						리포트 요청 실패. API 서버가 켜져 있는지 확인하세요.
					</p>
				)}

				{tree && (
					<>
						<header className="report-head">
							<p className="report-eyebrow">{tree.stamp.slice(0, 16).replace("T", " ")}</p>
							<h1 className="report-title">
								{tree.ticker}
								{tree.name ? ` · ${tree.name}` : ""}
							</h1>
							{tree.decision && (
								<span className={`ks-tag report-decision ${decisionClass(tree.decision)}`}>
									{tree.decision}
								</span>
							)}
						</header>

						<nav className="report-tabs" role="tablist">
							{sectionOrder.map((section) => (
								<button
									key={section}
									type="button"
									role="tab"
									aria-selected={section === activeSection}
									className={`report-tab ${section === activeSection ? "is-active" : ""}`}
									onClick={() => setActiveSection(section)}
								>
									{SECTION_LABELS[section] ?? section}
								</button>
							))}
						</nav>

						<div className="report-panel">
							{(filesBySection[activeSection] ?? []).map((file) => (
								<article key={file.path} className="report-article">
									<p className="article-path">{file.path}</p>
									<div
										className="article-body"
										// marked + DOMPurify sanitize — 런타임 XSS 차단
										dangerouslySetInnerHTML={{
											__html: DOMPurify.sanitize(
												marked.parse(file.content, { async: false }) as string,
											),
										}}
									/>
								</article>
							))}
						</div>
					</>
				)}
			</section>
		</div>
	);
}
