/**
 * #159 — 차트 포함 보고서(`complete_report.html`)를 웹 화면 안에 보여준다.
 *
 * HTML 보고서에만 시장·거시·재무 차트와 "한눈에 보기"가 있으므로 같은 파일을 가져와
 * `srcDoc` 로 띄운다. `fetch` 는 `Content-Disposition: attachment` 를 무시하므로 기존
 * 다운로드 엔드포인트를 그대로 쓴다 (API 변경 없음). `sandbox=""` 로 스크립트·폼·같은 출처
 * 접근을 모두 막는다 — 보고서 HTML 자체도 CSP `default-src 'none'` 이다.
 */

import { useEffect, useState } from "react";
import "./ReportFrame.css";

const API_BASE =
	(import.meta.env.PUBLIC_API_BASE as string | undefined) ??
	"http://localhost:8000";

interface Props {
	reportId: string;
}

type State =
	| { kind: "loading" }
	| { kind: "ready"; html: string }
	| { kind: "missing" }
	| { kind: "error" };

export default function ReportFrame({ reportId }: Props) {
	const [state, setState] = useState<State>({ kind: "loading" });

	useEffect(() => {
		const controller = new AbortController();
		setState({ kind: "loading" });
		fetch(`${API_BASE}/api/reports/${encodeURIComponent(reportId)}/download?format=html`, {
			signal: controller.signal,
		})
			.then(async (response) => {
				if (response.status === 404) {
					setState({ kind: "missing" });
					return;
				}
				if (!response.ok) throw new Error(String(response.status));
				setState({ kind: "ready", html: await response.text() });
			})
			.catch((error: unknown) => {
				if (error instanceof DOMException && error.name === "AbortError") return;
				setState({ kind: "error" });
			});
		return () => controller.abort();
	}, [reportId]);

	if (state.kind === "loading") return <p className="report-frame-note">차트 보고서를 불러오는 중…</p>;
	if (state.kind === "missing") {
		return (
			<p className="report-frame-note">
				이 보고서에는 차트 포함 HTML 이 없습니다 (차트 기능 이전에 만든 보고서). 다른 탭에서 본문을
				볼 수 있습니다.
			</p>
		);
	}
	if (state.kind === "error") {
		return (
			<p className="report-frame-note is-error">
				차트 보고서를 불러오지 못했습니다. API 서버가 켜져 있는지 확인하세요.
			</p>
		);
	}
	return (
		<iframe
			className="report-frame"
			title="차트 포함 보고서"
			sandbox=""
			srcDoc={state.html}
		/>
	);
}
