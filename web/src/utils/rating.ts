// 내부 등급 값(영어, 파서·백테스트 기준)을 화면용 한국어로 바꾼다 (#145).
// tradingagents/agents/rating.py 의 RATING_KO 와 같아야 한다.
const RATING_KO: Record<string, string> = {
	buy: "매수",
	overweight: "비중 확대",
	hold: "보유",
	underweight: "비중 축소",
	sell: "매도",
};

export function ratingLabel(decision: string | null | undefined): string {
	if (!decision) return "";
	return RATING_KO[decision.trim().toLowerCase()] ?? decision;
}
