/**
 * Task 14d (#109) — 종목명/종목코드 자동완성.
 *
 * 입력을 300ms debounce 로 `${API_BASE}/api/symbols/search` 에 요청하고
 * 결과를 리스트로 렌더링한다. 키보드 (↑/↓/Enter/Esc) 와 마우스 클릭 선택
 * 모두 지원. 선택된 종목은 `onSelect` 콜백과 `<input hidden>` 양쪽으로
 * 상위에 전달되어 14e 의 "분석 시작" 라우팅이 집어갈 수 있게 한다.
 */

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import "./SymbolSearch.css";

export interface SymbolHit {
	ticker: string;
	name: string;
	market: string;
}

interface Props {
	/** 선택이 끝난 뒤 상위에 알림. 14e 라우팅이 사용. */
	onSelect?: (hit: SymbolHit) => void;
}

interface SearchResponse {
	hits: SymbolHit[];
}

const API_BASE =
	(import.meta.env.PUBLIC_API_BASE as string | undefined) ??
	"http://localhost:8000";
const DEBOUNCE_MS = 300;
const LIMIT = 20;

export default function SymbolSearch({ onSelect }: Props) {
	const [query, setQuery] = useState("");
	const [hits, setHits] = useState<SymbolHit[]>([]);
	const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
	const [cursor, setCursor] = useState(0);
	const [selected, setSelected] = useState<SymbolHit | null>(null);
	const abortRef = useRef<AbortController | null>(null);

	useEffect(() => {
		const q = query.trim();
		if (!q) {
			setHits([]);
			setStatus("idle");
			return;
		}
		if (selected && selected.name === q) {
			// 사용자가 방금 리스트에서 고른 결과를 다시 쿼리하지 않는다.
			return;
		}
		const timer = window.setTimeout(() => {
			abortRef.current?.abort();
			const controller = new AbortController();
			abortRef.current = controller;
			setStatus("loading");
			const url = `${API_BASE}/api/symbols/search?q=${encodeURIComponent(q)}&limit=${LIMIT}`;
			fetch(url, { signal: controller.signal })
				.then((response) => {
					if (!response.ok) throw new Error(String(response.status));
					return response.json() as Promise<SearchResponse>;
				})
				.then((data) => {
					setHits(data.hits);
					setCursor(0);
					setStatus("idle");
				})
				.catch((err: unknown) => {
					if (err instanceof DOMException && err.name === "AbortError") return;
					setStatus("error");
				});
		}, DEBOUNCE_MS);
		return () => window.clearTimeout(timer);
	}, [query, selected]);

	function pick(hit: SymbolHit) {
		setSelected(hit);
		setQuery(hit.name);
		setHits([]);
		onSelect?.(hit);
	}

	function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
		if (!hits.length) return;
		if (event.key === "ArrowDown") {
			event.preventDefault();
			setCursor((c) => (c + 1) % hits.length);
		} else if (event.key === "ArrowUp") {
			event.preventDefault();
			setCursor((c) => (c - 1 + hits.length) % hits.length);
		} else if (event.key === "Enter") {
			event.preventDefault();
			pick(hits[cursor]);
		} else if (event.key === "Escape") {
			setHits([]);
		}
	}

	const showEmpty =
		status === "idle" && query.trim().length > 0 && hits.length === 0 && !selected;

	return (
		<div className="symbol-search">
			<label htmlFor="symbol-search-input" className="search-label">
				종목 검색
			</label>
			<input
				id="symbol-search-input"
				className="search-input"
				type="text"
				autoComplete="off"
				spellCheck={false}
				placeholder="예: 삼성전자, 005930, kodex"
				value={query}
				onChange={(event) => {
					setQuery(event.target.value);
					if (selected) setSelected(null);
				}}
				onKeyDown={onKeyDown}
				aria-expanded={hits.length > 0}
				aria-controls="symbol-listbox"
				aria-autocomplete="list"
			/>

			{status === "loading" && <p className="search-hint">검색 중…</p>}
			{status === "error" && (
				<p className="search-hint is-error">
					API 요청 실패. <code>uvicorn</code> 가 켜져 있는지 확인하세요.
				</p>
			)}
			{showEmpty && <p className="search-hint is-empty">검색 결과 없음</p>}

			{hits.length > 0 && (
				<ul
					id="symbol-listbox"
					role="listbox"
					className="search-list"
					aria-label="종목 검색 결과"
				>
					{hits.map((hit, i) => (
						<li
							key={hit.ticker}
							role="option"
							aria-selected={i === cursor}
							className={`search-row ${i === cursor ? "is-active" : ""}`}
							onMouseEnter={() => setCursor(i)}
							onClick={() => pick(hit)}
						>
							<span className="row-ticker">{hit.ticker}</span>
							<span className="row-name">{hit.name}</span>
							<span
								className={`ks-tag ${hit.market === "KOSPI" ? "is-ready" : "is-neutral"}`}
							>
								{hit.market}
							</span>
						</li>
					))}
					{hits.length === LIMIT && (
						<li className="search-hint is-more" aria-hidden="true">
							· 결과가 더 있을 수 있어요. 검색어를 더 좁혀 보세요.
						</li>
					)}
				</ul>
			)}

			{selected && (
				<p className="search-selected" aria-live="polite">
					선택됨 · <strong>{selected.ticker}</strong> {selected.name}
				</p>
			)}

			{/* 폼 제출/서버 라우팅용 hidden input — 14e 에서 활용. */}
			<input type="hidden" name="ticker" value={selected?.ticker ?? ""} />
		</div>
	);
}
