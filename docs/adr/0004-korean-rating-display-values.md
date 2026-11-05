# ADR-0004: 등급 값은 화면에서 한국어로 표기, 내부 값은 영어 유지

- 상태: Accepted (ADR-0003 의 "혼합 케이스 — 값은 영어" 를 대체)
- 날짜: 2026-11-05
- 관련 이슈/문서: #145, [[ADR-0003]], [[CLAUDE.md]] §4.1, [[GLOSSARY.md]] "최종 결정 라벨"

## 문제 상황 (Context)

ADR-0003 은 파서·백테스트·메모리 로그가 영어 값(`Buy`/`Underweight` 등)에 의존한다는 이유로 결정 라인의 **값을 영어로 유지**했다. 그 결과 보고서 제목 배지가 `Underweight`, 본문에 `Underweight`·`SELL` 이 반복 노출되는 등 사용자 노출 텍스트에 영어가 남았다. 사용자가 읽는 텍스트는 한국어여야 한다는 ADR-0003 의 원칙과 어긋난다.

ADR-0003 이 값 번역을 막은 근거는 "다운스트림 전부를 재작성해야 한다" 였다. 그러나 번역을 **경계 한 곳(파서)** 에서 흡수하면 다운스트림은 건드릴 필요가 없다.

## 결정 (Decision)

- **내부 값은 영어 그대로**: `Buy/Overweight/Hold/Underweight/Sell`. 구조화 출력 enum, `backtest`, 메모리 로그, `final_rating`, API 의 `decision` 은 모두 영어.
- **화면 표기는 한국어**: 매수 / 비중 확대 / 보유 / 비중 축소 / 매도 (`rating.py::RATING_KO`, `display_rating()`).
- **파서가 두 표기를 모두 읽는다**: `extract_rating` 은 `**등급**: 비중 축소` 와 `**등급**: Underweight` 를 같은 등급(`Underweight`)으로 반환한다. 한국어→내부 값 변환은 파서 한 곳.
- 렌더러(`schemas.py`)는 한국어 모드에서 값을 한국어로 쓴다. 영어 모드는 내부 값 그대로.
- 보고서 헤더(`- 등급: …`)·HTML 배지·웹 UI 는 한국어로 표시. API(`reports_store.rating_from_header_line`)는 한국어/영어 헤더를 모두 읽어 영어 값을 돌려주므로 **이전에 저장된 보고서도 그대로 동작**한다.
- 프롬프트는 본문 서술에 한국어 표기를 쓰게 한다. 구조화 필드(enum)의 값은 영어로 유지.

## 결과 (Consequences)

- 사용자가 보는 곳(제목·헤더·본문·UI)에서 영어 등급이 사라진다.
- 다운스트림 코드는 변경 없음. 새 소비자는 내부 값(영어)을 쓰고, 화면에 낼 때만 `display_rating()`.
- 센티먼트 값(`Bullish` 등)과 신뢰도도 같은 방식으로 한국어 표기(`SENTIMENT_BAND_KO`, `CONFIDENCE_KO`)를 쓴다.
- 새 표기를 추가하면 `RATING_KO`(파이썬)와 `web/src/utils/rating.ts` 두 곳을 맞춰야 한다.
