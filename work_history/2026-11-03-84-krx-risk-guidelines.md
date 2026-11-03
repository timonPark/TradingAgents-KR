# [#84] Task 9e: KRX 특유 리스크 지침 추가

- 이슈: https://github.com/timonPark/TradingAgents-KR/issues/84
- PR: (작업 완료 후 추가)
- 상위 에픽: #79
- 브랜치: `feat/84-krx-risk-guidelines`
- 작업 기간: 2026-11-03 ~

## 범위

Task 9d 로 전면 한국어화된 12개 에이전트 프롬프트에 **KRX 특유 리스크 지침**
추가. code_artifact.md Task 9 작업 내용에 명시된 5개 축:
1. 상·하한가 ±30% 제한
2. 관리종목 / 환기종목
3. 공매도 금지 종목
4. 외국인/기관 수급 공백 영향 (Task 6c 에서 투자자별 수급 선조회로 이미 커버)
5. 오버행 이슈 (대주주 매도 가능성)

### 에이전트별 지침 매핑

- **market_analyst**: ±30% 상·하한가 (가격 분석 왜곡), 공매도 금지가 가격 하락
  저항으로 작용함을 해석.
- **news_analyst**: 관리종목/환기종목 지정 뉴스, 상장폐지 사유, 대주주 블록딜/
  오버행 공시를 즉시 심각 리스크로 분류.
- **sentiment_analyst**: 기존 지침 ("관리종목 지정/감자/상장폐지 관련 뉴스는 즉시
  심각 리스크로") 를 확장 — 오버행/공매도 재개 등 추가.
- **trader**: 진입가/손절가 설정 시 ±30% 상·하한가 범위 고려, 공매도 금지로
  매도 호가 압력 제한.
- **리스크 디베이터 3**: 각 입장에서 KRX 리스크를 활용:
  - aggressive: ±30% 상한 미달인 극단 상승은 추가 upside 여지 주장
  - conservative: 관리종목/오버행 리스크를 적극 이슈 제기
  - neutral: KRX 특유 변동성 요인을 균형 평가

### scope 밖
- CLI UI 한국어화: Task 9f (#85)

## 수행한 변경

### `tradingagents/agents/analysts/market_analyst.py`

- 기존 KRX 투자자 수급 블록 아래에 "**KRX 특유 리스크 (가격 분석 시 반드시 고려)**"
  섹션 신규 추가:
  - ±30% 상·하한가가 당일 종가로는 모멘텀 진짜 강도를 가린다는 점. ATR/Bollinger
    밴드가 벽에서 포화. 다음 세션 갭·거래량 재개를 함께 보라는 지침.
  - 공매도 금지 종목의 하방 압력 완화 → 저항선이 평상시보다 견고. 금지 재개 공시
    발생 시 급락 리스크 — 뉴스 분석가 공시 섹션과 교차 확인.
  - 외국인 순매수 수일 0/음수 수렴 시 유동성 공급자 이탈 → 변동성 증폭 가능.

### `tradingagents/agents/analysts/news_analyst.py`

- system_message 중단에 "**KRX 특유 리스크 뉴스 (발견 시 즉시 심각 리스크로 분류)**"
  섹션 신규:
  - 관리종목 / 환기종목 지정 또는 사유 발생
  - 상장폐지 사유 공시 (가장 심각)
  - 대주주 매도 / 블록딜 / 보호예수 해제 (오버행)
  - 공매도 금지 재개 공시 (수일 하방 압력 급증, -10% 전후 전례)
  - 유상증자 / 전환사채(CB) 발행 (신주 희석)

### `tradingagents/agents/analysts/sentiment_analyst.py`

- 기존 "5. 촉매·리스크 분리" 섹션의 단일 bullet ("관리종목 지정/감자/상장폐지")
  을 **5개 KRX 특유 리스크 bullet** 로 확장:
  - 관리종목 / 환기종목 → 센티먼트 급격 Bearish 전환
  - 상장폐지 사유 → 가장 강한 Bearish
  - 대주주 매도 / 블록딜 / 보호예수 해제 → 상단 억제, 하방 지속
  - 공매도 금지 재개 → 수일 간 Bearish 유지
  - 유상증자 / CB 발행 → Mildly Bearish ~ Bearish (발행 조건 의존)
- 각 리스크를 `overall_band` / `confidence` 에 반영하라는 명시적 지침.

### `tradingagents/agents/trader/trader.py`

- 가격 포맷 규칙 뒤에 "**KRX 특유 리스크 (가격 수준 설정 시 반드시 반영)**" 섹션:
  - ±30% 상·하한가: 진입가 범위 **내** 지정, 손절가는 하한가 (-30%) 에서 안전
    여유 (예: -25% 이내) 필요 — 하한가 체결 불가로 보호 작동 안 할 수 있음.
  - 공매도 금지 종목에서 Sell 포지션은 대차·공매 경로 막혀 실행 비용 급증 →
    narrative 에 유보 조건 명시.
  - 공시 임박 종목은 진입 시점을 공시 직후로 미루는 것 고려.

### `tradingagents/agents/risk_mgmt/aggressive_debator.py`

- 토론 지침 바로 전에 "**KRX 특유 리스크 — 공격적 관점에서의 활용**" 섹션:
  - ±30% 상한을 "**보장된 손실 상한**" 으로 재프레이밍. 상한가 마감 종목의 익일
    갭 업 트레이드가 통계적으로 유리.
  - 공매도 금지로 매수 포지션의 **시간 가치**.
  - 관리종목 / 오버행은 "이미 반영" 가정으로 역발상 기회 주장.

### `tradingagents/agents/risk_mgmt/conservative_debator.py`

- 토론 지침 바로 전에 "**KRX 특유 리스크 — 보수적 관점에서 반드시 제기**" 섹션:
  - 관리종목/상장폐지 → **포지션 완전 손실 (-100%)** 가능 → 극단 꼬리 위험으로
    배제가 안전.
  - 오버행 → **매도 압력 규모 vs 일평균 거래대금** 비율로 공격적 역발상 반박.
  - 공매도 재개 → 수일간 -10% 전례, 시간 가치 주장 과소평가 지적.
  - ±30% → 단일 세션 -30% 는 한 달치 수익 즉시 제거. 손절 하한가 체결 불가 상기.

### `tradingagents/agents/risk_mgmt/neutral_debator.py`

- 토론 지침 바로 전에 "**KRX 특유 리스크 — 중립적 관점에서의 균형**" 섹션:
  - ±30% → 포트폴리오의 1-3% 수준 사이징으로 양측 논거 해소.
  - 관리종목 / 오버행 → 포지션 크기 축소 (평소 1/3 ~ 1/2) + 분할 진입. 공시
    리스크 규모와 가격 할인폭 비교.
  - 공매도 금지 → 분기 말 / 정책 발표 시점 전 축소 전략.
  - 수급 공백 → 3거래일 이상 외국인 순매수 전환 (턴어라운드 신호) 기다렸다 분할
    매수.

## 설계 결정 변경 사항

### 외국인/기관 수급 공백은 지침보다 선조회 데이터로

code_artifact.md Task 9 에 "외국인/기관 수급 공백 영향" 명시. Task 6c (#54) 가
이미 `get_investor_net_purchases` 를 market_analyst 선조회에 추가해 수급 데이터
자체는 자동 제공. market_analyst 와 neutral_debator 에서 **해석 지침** 추가로
보완 — 데이터는 선조회로, 해석은 프롬프트로 분리.

### 각 리스크 디베이터가 KRX 리스크를 자기 입장에서 다루도록

code_artifact.md 는 "리스크 디베이터에 지침 추가" 명시만. 세 디베이터 모두에게
동일 지침을 복사하면 토론이 평평해지는 문제 → 각 디베이터가 **자기 입장에서
KRX 리스크를 활용** 하도록 분화:
- aggressive: 리스크를 **기회로 재프레이밍** (손실 상한, 시간 가치, 역발상)
- conservative: 리스크를 **극단 꼬리 위험으로 강조** (완전 손실, 체결 불가)
- neutral: 리스크를 **사이징/타이밍으로 해소** (분할, 턴어라운드 신호)

이렇게 분화해야 이슈의 "토론" 요구 (단순 데이터 나열이 아님) 가 충족.

### 유상증자 / 전환사채 공시 추가 (code_artifact.md 명시 밖)

code_artifact.md 는 5개 축만 명시하지만, 유상증자 / CB 발행은 KRX 특유 희석 리스크
로 news_analyst 와 sentiment_analyst 에 함께 포함. Task 5 (DART) 로 CB 공시가
이미 fundamentals_analyst 선조회에 포함돼 있어, 센티먼트 / 뉴스 해석 지침과
자연스럽게 연결.

## 검증 결과

- `pytest -q` 전체 → **851 passed**
- `ruff check tradingagents cli tests` → **All checks passed**
- 수동 smoke: 5개 리스크 축이 각 에이전트 프롬프트에 적절히 분배됐는지 섹션별
  확인 (각 에이전트 파일에서 "KRX 특유 리스크" 검색 → 각 1건 이상).

## 완료 criteria 확인

### Task 9e (#84)
- ✓ **상·하한가 ±30% 제한**: market_analyst (가격 분석), trader (손절 설정),
  aggressive (손실 상한 재프레이밍), conservative (단일 세션 -30%), neutral
  (포지션 사이징) — **5개 에이전트** 커버.
- ✓ **관리종목 / 환기종목**: news_analyst (즉시 심각 리스크), sentiment_analyst
  (급격 Bearish), conservative (완전 손실 가능) — **3개 에이전트** 커버.
- ✓ **공매도 금지 종목**: market_analyst (하방 압력 완화), news_analyst (재개
  공시 급락), trader (Sell 실행 비용 급증), aggressive (시간 가치), conservative
  (재개 리스크), neutral (분기 말 축소) — **6개 에이전트** 커버.
- ✓ **외국인/기관 수급 공백 영향**: market_analyst 섹션에 "외국인 순매수 수일
  수렴 → 유동성 공급자 이탈" 추가. neutral_debator 에서 "턴어라운드 신호"
  활용 지침. 데이터는 Task 6c 가 이미 선조회로 제공.
- ✓ **오버행 (대주주 매도 가능성)**: news_analyst (블록딜/보호예수 해제),
  sentiment_analyst (상단 억제), conservative (매도 압력 규모) — **3개 에이전트**
  커버.

## 다음 작업 핸드오프

### Task 9f (#85): CLI UI 한국어화
- `cli/display.py` (622 lines), `cli/prompts.py` (349 lines), `cli/selections.py`
  (260 lines), `cli/run.py` (465 lines), `cli/prefs.py` (92 lines), `cli/main.py`
  사용자 노출 메시지.
- Rich 콘솔 표 / 제목 / 진행 메시지 / 선택 프롬프트 / 에러 메시지 전수 한국어화.
- CLI 플래그 이름 / 환경변수 이름 / 코드 식별자는 영어 유지.

