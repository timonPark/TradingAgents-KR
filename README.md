<p align="center">
  <img src="tradingagents/assets/tauric-logo.svg" width="60%" alt="Tauric Research">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="https://github.com/TauricResearch/TradingAgents" target="_blank"><img alt="Upstream" src="https://img.shields.io/badge/Upstream-TauricResearch%2FTradingAgents-14C290?logo=github"/></a>
  <img alt="Market" src="https://img.shields.io/badge/Market-KOSPI%20%7C%20KOSDAQ-blue"/>
  <img alt="Status" src="https://img.shields.io/badge/Status-WIP-orange"/>
</div>

---

# TradingAgents-KR: 한국 증시용 멀티 에이전트 트레이딩 프레임워크

## 🙏 기반 프로젝트 (Based on)

**본 프로젝트는 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 를 기반으로 제작된 한국판 포크(fork)입니다.**

- 📦 **Upstream 저장소**: https://github.com/TauricResearch/TradingAgents
- 👥 **원 저작자**: Tauric Research (Yijia Xiao, Edward Sun, Di Luo, Wei Wang)
- 📄 **원 논문**: [TradingAgents: Multi-Agents LLM Financial Trading Framework (arXiv:2412.20138)](https://arxiv.org/abs/2412.20138)
- 📜 **라이선스**: Apache 2.0 (upstream 원 라이선스 그대로 승계, `LICENSE` 참조)

원본 프레임워크의 **핵심 추론 엔진(LangGraph 오케스트레이션, 멀티 에이전트 토론·리스크 관리 파이프라인)은 그대로 유지**한 채, **데이터 수집 레이어만 한국 증시(KOSPI/KOSDAQ) 환경으로 전환**한 커스터마이징 버전입니다. 원 저작자의 설계와 연구 성과에 깊은 감사를 표합니다.

---

> ⚠️ **진행 상태 (WIP)**: 데이터 소스 교체 작업이 진행 중입니다. 아래 "커스터마이징 범위" 섹션의 Task 체크리스트를 참고하세요. 아직 완료되지 않은 Task 는 upstream 의 원본 동작(미국 증시 기준)으로 동작합니다.

---

## 🚀 Quick Start

**전제조건이 이미 다 준비된 경우** 쓰는 최단 경로입니다. 처음이라면 아래 ["설치 및 실행"](#설치-및-실행) 7단계를 먼저 따라가세요.

전제: Python 3.11+, Node.js 22.23.4+, [`claude` CLI 로그인 완료](#4-claude-code-cli-설치-및-로그인-필수), `.env` 에 `DART_API_KEY` 설정.

### 옵션 A — CLI 로 분석

```bash
source .venv/bin/activate
tradingagents          # 종목명(예: "삼성") 또는 6자리 코드 입력 → 분석 시작
```

### 옵션 B — 로컬 웹 UI (Astro + FastAPI, Neo Kinpaku 디자인)

> ⚠️ **터미널 두 개를 동시에 열어 각각 띄워 둬야 합니다.** 백엔드(uvicorn)와 프론트엔드(Astro dev 서버)는 별도 프로세스입니다. 하나라도 꺼져 있으면 UI 에서 "API 요청 실패. uvicorn 가 켜져 있는지 확인하세요" 가 뜹니다.

#### 🖥️ 터미널 1 — 백엔드 (FastAPI, 포트 8000)

```bash
cd /Users/2309-n0018/Project/TradingAgents-KR
source .venv/bin/activate
pip install -e ".[web]"     # 첫 실행 시 한 번만
uvicorn api.main:app --reload --port 8000
```

정상 기동 로그 예시:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

#### 🌐 터미널 2 — 프론트엔드 (Astro, 포트 4321)

```bash
cd /Users/2309-n0018/Project/TradingAgents-KR/web
npm install                 # 첫 실행 시 한 번만
npm run dev
```

#### 🔗 접속

브라우저에서 **http://localhost:4321** 접속 → 종목 검색 → 분석 설정 → **"분석 시작"** → 라이브 진행 확인. 저장된 리포트는 **http://localhost:4321/report** 에서 사이드바로 열람.

> 💡 **처음 테스트**는 쿼터 절감을 위해 UI 의 `effort` 를 `low` 로 낮춰 돌리는 걸 추천합니다. Claude Code Max/Pro 쿼터를 소모합니다.

#### 문제 해결

- **"API 요청 실패"** → 터미널 1 의 uvicorn 로그가 살아있는지 확인. 꺼졌으면 다시 실행.
- **포트 8000 이 다른 프로그램 점유 중** → uvicorn 을 `--port 8001` 로 바꾸고 `web/.env` 에 `PUBLIC_API_BASE=http://localhost:8001` 추가 후 `npm run dev` 재시작.
- **`uvicorn: command not found`** → `source .venv/bin/activate` 를 안 한 것. venv 활성화부터 다시.

---

## 커스터마이징 범위

TauricResearch 의 원본 프레임워크 대비 다음 레이어를 한국 환경으로 교체합니다.

| 영역 | upstream (원본) | TradingAgents-KR |
|---|---|---|
| LLM 백엔드 | Anthropic/OpenAI/Google/Azure/Bedrock 등 15+ provider | **Claude Code 헤드리스 단일** (OAuth, Max/Pro 플랜 쿼터, ADR-0001) |
| 티커 포맷 | `^[A-Z]{1,5}$` (AAPL, NVDA) | `^\d{6}$` (005930, 035720) |
| 재무/공시 | SEC EDGAR | 금융감독원 Open DART (`OpenDartReader`) |
| 시세/보조지표 | Alpha Vantage, Yahoo Finance | `pykrx` (일봉 OHLCV + 투자자별 수급) |
| 센티먼트 | Reddit, StockTwits | 네이버 금융 주요 뉴스 |
| 거시지표 | FRED | 한국은행 ECOS API |
| 거래소 캘린더 | NYSE | KRX (한국거래소 영업일) |
| 에이전트 프롬프트 | 영어, 미국 시장 페르소나 | 한국어, 국내 증시 리스크(수급 공백·오버행·관리/환기종목) 반영 |

### 작업 체크리스트

- [ ] **Task 1** — 티커 유효성 검증 정규식을 한국 6자리 종목코드로 변경
- [ ] **Task 2** — 재무/공시 분석 도구 교체 (SEC EDGAR → OpenDartReader)
- [ ] **Task 3** — 시세 및 기술적 지표 도구 교체 (Alpha Vantage/Yahoo → pykrx) + 외국인/기관 수급 통합
- [ ] **Task 4** — 거시경제·뉴스 도구 현지화 (ECOS + 네이버 금융)
- [ ] **Task 5** — 거래소 캘린더 KRX 매핑 (백테스트 시점 격리)
- [ ] **Task 6** — 시스템 프롬프트 한국어 전환 및 국내 리스크 페르소나 보강

---

## 프레임워크 개요

TradingAgents 는 실제 트레이딩 하우스의 조직 구조를 모방한 멀티 에이전트 프레임워크입니다. 펀더멘털 분석가, 센티먼트 전문가, 기술적 분석가에서부터 트레이더와 리스크 관리팀까지, 역할이 분화된 LLM 에이전트들이 협업하여 시장 상황을 평가하고 매매 의사결정을 내립니다. 에이전트들은 동적 토론을 통해 최적 전략을 도출합니다.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> 본 프레임워크는 연구 목적으로 설계되었습니다. 성능은 백본 모델, 모델 온도(temperature), 매매 기간, 데이터 품질 등 수많은 비결정적 요인에 따라 달라집니다. **금융·투자·매매 자문이 아닙니다.**

### 에이전트 조직

**분석가 팀 (Analyst Team)**
- **펀더멘털 분석가**: 기업 재무제표와 성과 지표를 평가하여 내재가치와 잠재적 리스크 요인을 식별합니다. (한국판에서는 DART 사업보고서/분기보고서 기반)
- **센티먼트 분석가**: 뉴스 헤드라인을 집계하여 단기 시장 심리를 측정합니다. (한국판에서는 네이버 금융 주요 뉴스 기반)
- **뉴스 분석가**: 거시경제 지표와 글로벌 뉴스를 모니터링하며 시장 영향을 해석합니다. (한국판에서는 한국은행 ECOS 지표 반영)
- **기술적 분석가**: RSI, MACD 등 기술적 지표로 매매 패턴을 감지하고 가격 흐름을 전망합니다. (한국판에서는 외국인/기관 5거래일 순매수 동향 추가)

선택된 분석가들은 각자의 도구로 병렬 작업하며, 모든 리포트가 모이면 리서치 토론이 시작됩니다.

**리서처 팀 (Researcher Team)**
- 강세론자(bull)와 약세론자(bear) 리서처가 분석가 팀의 인사이트를 비판적으로 검토합니다. 구조화된 토론을 통해 잠재 이익과 내재 리스크를 저울질합니다.

**트레이더 에이전트 (Trader Agent)**
- 분석가와 리서처의 리포트를 종합하여 매매 타이밍과 규모를 결정합니다.

**리스크 관리 및 포트폴리오 매니저**
- 변동성·유동성 등 리스크 요인을 지속적으로 평가하고 전략을 조정합니다. 포트폴리오 매니저가 최종 승인/거부를 결정하면 모의 거래소로 주문이 전송됩니다.

---

## 설치 및 실행

### 1. 저장소 복제

```bash
git clone <this-repo-url> TradingAgents-KR
cd TradingAgents-KR
```

### 2. Python 환경 (3.11 이상)

```bash
conda create -n tradingagents-kr python=3.13
conda activate tradingagents-kr
```

또는 [uv](https://docs.astral.sh/uv/) 사용:

```bash
uv venv --python 3.13
source .venv/bin/activate
```

### 3. 패키지 설치

```bash
pip install .
```

### 4. Claude Code CLI 설치 및 로그인 (필수)

TradingAgents-KR 은 Claude Code 헤드리스를 **유일한 LLM 백엔드**로 사용합니다 (ADR-0001). 로컬에 Claude Code CLI 를 설치하고 로그인하면 `.env` 에 LLM API 키를 둘 필요가 없습니다 — OAuth 토큰이 자격증명 역할을 합니다.

```bash
npm install -g @anthropic-ai/claude-code
claude login            # Max/Pro 플랜 또는 Pro 구독으로 OAuth 로그인
claude -p "ping"        # 설치 및 인증 확인
```

### 5. 한국 데이터 소스용 추가 라이브러리

```bash
pip install pykrx OpenDartReader finance-datareader
```

### 6. 데이터 API 키 발급 및 `.env` 설정

```bash
# 한국 데이터 소스
export DART_API_KEY=...            # 금융감독원 Open DART 인증키 (필수)
export ECOS_API_KEY=...            # 한국은행 ECOS API 인증키 (선택)
export NAVER_API_HUB_CLIENT_ID=... # NAVER API HUB 뉴스 검색 Client ID (선택)
export NAVER_API_HUB_CLIENT_SECRET=...  # NAVER API HUB 뉴스 검색 Client Secret (선택)
```

- **DART 인증키 발급**: [opendart.fss.or.kr](https://opendart.fss.or.kr/) 에서 무료 발급
- **ECOS 인증키 발급**: [ecos.bok.or.kr](https://ecos.bok.or.kr/) 에서 무료 발급
- **NAVER API HUB 키 발급**: NCP 콘솔 > NAVER API HUB > Application 등록 (카테고리 `NAVER 검색` > `뉴스`) 후 [인증 정보] 에서 확인. 네이버 검색 오픈 API 는 2026-07-31 부터 개발자센터 신규 신청이 막히고 NAVER API HUB 로 이관됐습니다. 키가 없으면 네이버 증권 뉴스(keyless)로 자동 폴백합니다.

> ⚠️ **LLM API 키는 설정하지 마세요.** `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` 등은 Task 2 (#21) 로 코드베이스에서 제거되었고 참조되지 않습니다. 유일한 예외는 디버깅용 `TRADINGAGENTS_CLAUDE_BARE=1` escape hatch 가 `ANTHROPIC_API_KEY` 를 요구하는 경우입니다 (CLAUDE.md §4.6).

### 7. Docker 로 실행 (선택)

컨테이너 내부에 Node.js 와 `@anthropic-ai/claude-code` 를 사전 설치해 둔 이미지가 제공됩니다. 호스트의 Claude Code OAuth credential 을 **읽기전용** 으로 공유해 컨테이너 안에서 그대로 Max/Pro 플랜 쿼터를 사용합니다.

**사전 요구사항:**
- 호스트에 Claude Code CLI 설치 + `claude login` 완료 (`~/.claude/.credentials.json` 생성).
- Docker Engine 24+ 와 docker compose 플러그인.

**실행:**

```bash
# 1. 이미지 빌드
docker compose build

# 2. CLI 대화형 실행 (호스트 ~/.claude/.credentials.json 자동 마운트)
docker compose run --rm tradingagents

# 3. 플래그로 비대화형 실행
docker compose run --rm tradingagents \
    --ticker 005930 --date 2026-11-03 --analysts market,news --save --no-show
```

**credential 공유 방식:**
- 호스트의 `~/.claude/.credentials.json` 만 `/claude-auth/.credentials.json` 로 읽기전용 마운트.
- 컨테이너는 `HOME=/tmp/claude-home` 를 쓰기 가능한 임시 디렉터리로 지정하고, `docker/entrypoint.sh` 가 symlink 로 credential 을 연결.
- Claude Code 가 세션/캐시/리프레시 상태를 쓰더라도 `/tmp/claude-home/.claude/` 로 가므로 **호스트 `~/.claude` 는 오염되지 않음**.
- 컨테이너 종료 시 임시 상태 소실.

> ⚠️ **"HOME 재지정만으로 OAuth 리프레시 토큰 쓰기 정상 작동" 가정은 검증 전**입니다. 실제 리프레시 실패 시 `docker-compose.yml` 의 credential 마운트를 `${HOME}/.claude:/claude-auth:ro` (디렉터리 전체) 로 바꾸거나, `~/.claude` 전체를 **읽기쓰기** 로 마운트하는 방식으로 backoff 하세요 (호스트 상태 오염 위험 수용).

> **ollama 지원은 제거되었습니다** (Task 12). 과거 `ollama` / `tradingagents-ollama` 서비스와 `--profile ollama` 는 ADR-0001 에 따라 docker-compose.yml 에서 삭제됐습니다. Claude Code 가 유일한 LLM 백엔드입니다.

---

## CLI 사용법

대화형 CLI 실행:

```bash
tradingagents          # 설치 후 사용 가능한 명령
python -m cli.main     # 또는 소스에서 직접 실행
```

종목코드/종목명, 분석 날짜, 리서치 깊이, 모델/effort 등을 선택할 수 있는 화면이 나타납니다. 직전 실행의 응답이 기본값으로 복원되므로 Enter 만 누르면 그대로 재사용됩니다.

예시 (한국 종목):

```bash
tradingagents --ticker 005930 --date 2026-11-01 --analysts market,news,fundamentals --save
```

### 지원 티커 형식

TradingAgents-KR 은 한국거래소(KRX) 상장 종목을 기본 지원합니다.

- **KOSPI/KOSDAQ**: 6자리 숫자 코드 (예: `005930` 삼성전자, `035720` 카카오, `247540` 에코프로비엠)
- 미국·홍콩·상해 등 해외 종목은 **지원하지 않습니다** (Task 4, 하드 포크 결정 ADR-0001). KRX 외 티커를 입력하면 CLI 가 거부합니다.

### 종목명 검색 (Task 14g / #112)

**대화형 CLI** 에서는 6자리 종목코드 대신 **종목명 (한글/영문)** 을 입력할 수 있습니다. 매칭된 종목 목록이 나오면 번호로 선택합니다.

예:

```
KRX 종목코드 또는 종목명을 입력하세요 (예: 005930 (삼성전자), ...): 삼성

종목을 선택하세요:
  ❯ 005930 · 삼성전자 · KOSPI
    006400 · 삼성SDI · KOSPI
    028260 · 삼성물산 · KOSPI
    032830 · 삼성생명 · KOSPI
    ...
```

- 매칭 1건 → 자동 선택 + Y/N 확인
- 매칭 2–20건 → 번호 리스트에서 선택 (↑/↓/Enter/Esc)
- 매칭 0건 → "검색 결과 없음" 안내 후 재입력
- 매칭 20건 이상 → 상위 20개 + "더 좁혀서 검색하세요" 안내

**비대화형 `--ticker` 플래그는 여전히 6자리 숫자만 받습니다** — 자동화 스크립트의 결정성을 유지하기 위함.

데이터는 `~/.tradingagents/cache/krx_tickers_YYYYMMDD.json` 에 **하루 1회** 캐시됩니다.

---

## 로컬 웹 UI (Astro + FastAPI) — Task 14 / #105

CLI 외에 종목 검색·분석 실행·라이브 진행·리포트 열람을 **브라우저에서** 하고 싶다면 로컬 웹 UI 를 띄울 수 있습니다. Impeccable Neo Kinpaku 디자인 시스템 적용.

### 사전 요구사항

- Python 3.11+ 의존성 + `[web]` extra: `pip install -e ".[web]"`
- Node.js 22.23.4+ (Astro 7.4+ 요구)

### 기동 — 터미널 두 개

```bash
# 터미널 1: FastAPI 백엔드 (포트 8000)
source .venv/bin/activate
uvicorn api.main:app --reload --port 8000

# 터미널 2: Astro 프론트엔드 (포트 4321)
cd web && npm install && npm run dev
```

### 사용 흐름

1. `http://localhost:4321` 접속 → **홈**
2. 종목 검색 박스에 종목명 또는 6자리 코드 입력 → 자동완성에서 선택
3. 분석 날짜 / 분석가 체크박스 / 모델(sonnet·opus·haiku) / effort 선택 → **"분석 시작"**
4. 라이브 진행 패널에 노드 전환이 kinpaku 체크로 표시됨
5. 완료 후 `http://localhost:4321/report` 에서 과거 리포트 사이드바 열람 가능

### 환경변수 (선택)

- `TRADINGAGENTS_API_PORT` — FastAPI 포트 (기본 8000)
- `TRADINGAGENTS_API_CORS_ORIGINS` — 콤마로 구분된 허용 origin (기본 `http://localhost:4321`)
- `PUBLIC_API_BASE` (`web/.env`) — 프론트가 가리킬 API base URL (기본 `http://localhost:8000`)

### 범위 및 한계

- **로컬 전용**. 인증/배포/멀티테넌시 미지원.
- **Claude Code OAuth 쿼터**를 소모합니다. 깊이와 분석가 수에 따라 1회 분석이 수십 메시지~수백 메시지 소모 가능. 저비용 테스트는 `effort: low` 로 조정하세요.
- 프로세스 재시작 시 **인메모리 run 상태** 는 사라지지만, **디스크 리포트 트리**는 유지되어 `/report` 에서 계속 열람 가능.

---

## Python API 사용

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# 삼성전자 분석 예시
state, decision = ta.propagate("005930", "2026-11-01")
print(decision)

# CLI 가 저장하는 것과 동일한 리포트 트리
ta.save_reports(state, "005930")
```

설정 커스터마이징:

```python
config = DEFAULT_CONFIG.copy()
# llm_provider 는 "claude-code" 로 고정 (ADR-0001) — config 로 변경 불가.
config["deep_think_llm"] = "opus"       # sonnet / opus / haiku 또는 전체 ID
config["quick_think_llm"] = "haiku"
config["effort"] = "max"                # deep 티어: low/medium/high/xhigh/max
config["quick_effort"] = "medium"       # quick 티어
config["max_debate_rounds"] = 2
config["output_language"] = "Korean"    # 디폴트도 Korean

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("005930", "2026-11-01")
```

모든 설정 옵션은 `tradingagents/default_config.py` 를 참고하세요.

---

## 공시 데이터 (DART)

한국판에서는 SEC EDGAR 대신 금융감독원 **Open DART** 를 공시 데이터 원천으로 사용합니다. 최근 사업보고서/분기보고서로부터 다음 지표를 추출합니다.

- 최근 분기 매출액
- 영업이익률
- 부채비율
- 재고자산 추이
- 전환사채(CB) 발행 내역

> `DART_API_KEY` 가 설정되지 않으면 Task 2 데이터 수집이 실패합니다. 발급은 무료이며 즉시 가능합니다.

---

## 지속성 및 복구

### 메모리 로그

메모리 로그는 항상 활성화되어 있습니다. 완료된 각 실행의 의사결정이 `~/.tradingagents/memory/trading_memory.md` 에 추가됩니다. 이후 실행 시 보유 기간이 지난 결정의 실현 수익률(원시 수익률 및 KOSPI/KOSDAQ 벤치마크 대비 알파)과 1문단 성찰이 자동으로 집계됩니다.

경로 변경: `TRADINGAGENTS_MEMORY_LOG_PATH`

### 체크포인트 재개

`--checkpoint` 플래그로 활성화합니다. LangGraph 가 각 노드 이후 상태를 저장하므로, 중단된 실행이 처음부터 다시 시작하지 않고 마지막 성공 지점에서 재개됩니다.

```bash
tradingagents --checkpoint           # 이번 실행에서 활성화
tradingagents --clear-checkpoints    # 실행 전 초기화
```

---

## 테스트

### 유닛 테스트 (CI 기본)

유닛 테스트는 전부 모킹되어 있어 네트워크 호출 없이 빠르게 돌아갑니다.

```bash
pytest -q                      # 유닛 테스트만 (통합 테스트는 skip)
pytest tests/test_dart_vendor.py -q  # 특정 vendor 유닛 테스트만
```

CI (`.github/workflows/ci.yml`) 는 py3.11/3.12/3.13/3.14 매트릭스에서 `pytest -q`
를 돌립니다. 통합 테스트는 자동 skip 됩니다.

### opt-in 통합 테스트 (실제 API 호출)

Task 11 (#91): 실제 외부 API 를 호출하는 테스트는 `@pytest.mark.integration` 으로
분리됐습니다. 로컬에서 수동 실행하거나 nightly 돌리는 용도.

```bash
# 전부 실행 (설정된 환경변수에 따라 일부는 skip)
pytest -m integration -q

# 특정 vendor 만
pytest tests/test_pykrx_vendor.py -m integration -q
```

**vendor 별 요구사항:**

| Vendor | 요구 환경변수 / 전제 조건 | 환경 미구성 시 |
|---|---|---|
| **pykrx** (OHLCV / 기술지표) | 없음 (keyless) | 항상 실행 |
| **네이버뉴스** (네이버 증권 종목 뉴스 JSON) | 없음 (keyless) | 항상 실행 |
| **NAVER API HUB** (뉴스 검색) | `NAVER_API_HUB_CLIENT_ID` / `NAVER_API_HUB_CLIENT_SECRET` | `pytest.skip` |
| **DART** (재무 / 공시) | `DART_API_KEY` — https://opendart.fss.or.kr/ 발급 | `pytest.skip` |
| **ECOS** (한국은행 거시) | `ECOS_API_KEY` — https://ecos.bok.or.kr/ 발급 | `pytest.skip` |
| **Claude Code** (LLM 어댑터) | `claude` CLI PATH 등록 + Max/Pro OAuth 로그인 | `pytest.skip` |

**주의:**
- 통합 테스트는 **실제 API 쿼터** 를 소모합니다. DART (하루 20,000 회) / ECOS /
  Claude Code (Max 플랜 메시지 한도) 를 자주 돌리면 상한에 걸릴 수 있습니다.
- 네이버뉴스 크롤러는 ToS 준수 범위 내 저속 호출만 — 과도한 반복 실행 금지.

---

## 재현성에 관한 참고사항

TradingAgents 는 LLM 기반이므로 동일 종목·동일 날짜의 두 실행 결과가 다를 수 있습니다. 이는 언어 모델 기반 연구 도구의 특성이며 결함이 아닙니다. 차이의 원인은 다음과 같습니다.

- **모델 샘플링의 비결정성**: 고정 temperature 에서도 공급자는 바이트 단위 동일 출력을 보장하지 않습니다. 특히 reasoning 모델은 내부 추론 자체가 샘플링됩니다.
- **라이브 데이터 변화**: 뉴스와 거시 지표는 시간이 지나면 내용이 달라집니다. 분석 날짜를 고정해도 뉴스·센티먼트 소스는 "현재" 를 반영합니다.

재현성을 높이려면 `temperature` 를 낮추거나 non-reasoning 모델을 지정하세요.

---

## Upstream 과의 관계

본 저장소는 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 의 포크입니다. 다음 사항을 유지합니다.

- 핵심 아키텍처 (LangGraph 오케스트레이션, 에이전트 토론 구조)
- Apache 2.0 라이선스 (`LICENSE` 참조)
- 학술 인용 (아래 Citation)

변경 사항은 데이터 레이어와 프롬프트 현지화에 한정합니다. upstream 의 로직 개선·버그 수정 반영은 주기적으로 rebase/merge 를 통해 흡수합니다.

---

## Citation

원 저작자의 연구에 기반하므로, 학술적으로 참고 시 반드시 다음을 인용해 주세요.

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework}, 
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138}, 
}
```

---

## 면책 조항

본 소프트웨어는 연구·교육 목적으로 제공되며, 투자 자문이나 금융 상품의 매수/매도 권유가 아닙니다. 본 코드로 수행된 분석에 근거한 투자 결과에 대해 저작자 및 기여자는 어떠한 법적 책임도 지지 않습니다. 실제 투자 결정은 본인의 판단과 책임 하에 수행하시기 바랍니다.
