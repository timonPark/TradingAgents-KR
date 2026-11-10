<p align="center">
  <img src="tradingagents/assets/tauric-logo.svg" width="60%" alt="Tauric Research">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="https://github.com/TauricResearch/TradingAgents" target="_blank"><img alt="Upstream" src="https://img.shields.io/badge/Upstream-TauricResearch%2FTradingAgents-14C290?logo=github"/></a>
  <img alt="Market" src="https://img.shields.io/badge/Market-KOSPI%20%7C%20KOSDAQ-blue"/>
</div>

---

# TradingAgents-KR

**DART 공시, KRX 시세·외국인/기관 수급, 네이버 뉴스, 한국은행 거시지표를 종합해 한국 증시(KOSPI/KOSDAQ) 종목 분석 리포트를 생성하는 멀티 에이전트 프레임워크**입니다.

[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)의 핵심 추론 엔진(LangGraph 오케스트레이션, 멀티 에이전트 토론·리스크 관리 파이프라인)을 기반으로, 데이터 수집 레이어와 에이전트 프롬프트를 한국 증시 환경에 맞게 재설계한 하드 포크(hard fork)입니다. 외부 LLM API 키 대신 **Claude Code CLI 헤드리스(OAuth)**를 단일 백엔드로 사용하여 Claude Max/Pro 구독 쿼터로 동작합니다.

> ⚠️ **면책 고지**: 본 프로젝트는 연구·교육 목적으로 설계되었습니다. 생성된 리포트와 등급은 금융·투자 자문이나 매수/매도 권유가 아니며, 모든 투자 결정과 책임은 사용자 본인에게 있습니다.

---

## 빠른 시작 (Quick Start)

Python 3.11+, [`claude` CLI 로그인](#2-claude-code-cli-설치-및-로그인), `.env`의 `DART_API_KEY`가 준비된 환경에서의 최단 실행 경로입니다. 처음 설정한다면 아래 [설치 및 환경 설정](#설치-및-환경-설정)을 먼저 진행하세요.

```bash
# 1. 가상환경 활성화
source .venv/bin/activate

# 2-A. 대화형 CLI로 분석 실행 (종목명 "삼성" 또는 종목코드 "005930" 입력)
tradingagents

# 2-B. 플래그로 즉시 분석 실행
tradingagents --ticker 005930 --date 2026-11-01 --analysts market,news,fundamentals --save
```

브라우저에서 검색·실행·리포트 열람(PDF 다운로드 포함)을 하려면 [로컬 웹 UI](#2-로컬-웹-ui-astro--fastapi) 섹션을 참고하세요.

---

## 프레임워크 개요 및 한국화 범위

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;" alt="TradingAgents Architecture">
</p>

### 멀티 에이전트 파이프라인

각 노드는 역할과 추론 깊이(`deep_think_llm` / `quick_think_llm`)가 분리되어 단계별로 협업합니다.

1. **분석가 팀 (Analyst Team — 사전조회 패턴)**
   LLM이 툴을 반복 호출하는 대신, Python이 데이터를 사전 조회하여 프롬프트에 주입함으로써 호출 비용을 줄이고 환각을 방지합니다.
   - **재무(Fundamentals) 분석가**: DART 사업/분기보고서 기반 매출·영업이익률·부채비율·재고자산 추이·CB 발행 내역 및 원문 발췌 기반 회사 개요 분석
   - **시세(Market) 분석가**: `pykrx` 일봉 OHLCV, 기술적 지표(RSI, MACD, 볼린저 밴드 등), 외국인·기관·개인 최근 5거래일 순매수 수급 분석
   - **뉴스(News) 분석가**: 종목 주요 뉴스, 최근 30일 DART 공시, 한국은행 ECOS 거시지표(기준금리·환율·물가 등) 해석
   - **센티먼트(Sentiment) 분석가**: 종목 뉴스 헤드라인 기반 단기 시장 심리 평가
2. **리서처 팀 (Researcher Team)**
   - **강세(Bull) / 약세(Bear) 리서처**: 분석가 리포트를 바탕으로 매수·매도 논거를 구조화하여 다회차 토론 수행
   - **리서치 매니저**: 토론을 종합해 투자 논리와 추천 등급 도출
3. **트레이더 (Trader)**
   - 분석 결과와 현재 포트폴리오(선택)를 반영해 구체적인 매매 타이밍과 비중 제안
4. **리스크 관리 팀 & 포트폴리오 매니저 (Risk & Portfolio Manager)**
   - **공격적(Aggressive) / 보수적(Conservative) / 중립(Neutral) 디베이터**: 변동성·유동성·국내 증시 특유 리스크(수급 공백, 오버행, 관리/환기종목 등)를 다각도로 검증
   - **포트폴리오 매니저**: 최종 5단계 등급(`매수`/`비중 확대`/`보유`/`비중 축소`/`매도`) 및 거래 의사결정 확정

### Upstream 대비 변경 사항

| 영역 | Upstream (`TauricResearch/TradingAgents`) | `TradingAgents-KR` |
|---|---|---|
| **LLM 백엔드** | OpenAI / Anthropic / Google 등 15+ API SDK | **Claude Code 헤드리스 단일** (OAuth, Max/Pro 쿼터 활용) |
| **데이터 수집 방식** | LangGraph `ToolNode` 반복 호출 | **사전조회(Pre-fetch) + 프롬프트 주입** (분석가당 LLM 호출 1회) |
| **티커 포맷** | 미국 등 글로벌 티커 (`AAPL`, `0700.HK`) | **KRX 6자리 코드** (`^[0-9A-Z]{6}$`, 예: `005930`, `0126Z0`) |
| **재무 / 공시** | SEC EDGAR, Yahoo Finance | **금융감독원 Open DART** (`OpenDartReader`) |
| **시세 / 수급** | Alpha Vantage, Yahoo Finance | **`pykrx`** (일봉 OHLCV·기술지표 + 투자자별 수급, 네이버 증권 폴백) |
| **뉴스 / 센티먼트** | Reddit, StockTwits, Google News | **NAVER API HUB 뉴스 검색** + **네이버 증권 뉴스** (자동 폴백) |
| **거시지표** | FRED | **한국은행 ECOS API** (기준금리, 원/달러 환율, CPI, 국고채 금리) |
| **거래소 캘린더** | NYSE | **KRX 영업일 캘린더** (`exchange_calendars` `XKRX`) |
| **출력 및 UI** | 영어 리포트, CLI | **한국어 리포트** (원문 인용 검증 포함), **CLI 종목명 검색**, **로컬 웹 UI** |

---

## 설치 및 환경 설정

### 1. 저장소 복제 및 Python 패키지 설치

Python **3.11 이상**이 필요합니다.

```bash
git clone https://github.com/timonPark/TradingAgents-KR.git
cd TradingAgents-KR

# 가상환경 생성 및 활성화 (uv 또는 venv / conda)
uv venv --python 3.13
source .venv/bin/activate

# 코어 패키지 설치 (pykrx, OpenDartReader, finance-datareader 등 포함)
pip install -e .

# 로컬 웹 UI(FastAPI + PDF 변환)까지 사용할 경우
pip install -e ".[web]"
```

### 2. Claude Code CLI 설치 및 로그인

본 프로젝트는 외부 LLM API 키(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY` 등)를 사용하지 않습니다. 로컬에 설치된 Claude Code CLI의 OAuth 인증을 통해 동작합니다.

```bash
npm install -g @anthropic-ai/claude-code
claude login            # Claude Max/Pro 계정으로 OAuth 로그인
claude -p "ping"        # 정상 응답 확인
```

### 3. 환경변수 (`.env`) 설정

`.env.example`을 복사해 `.env` 파일을 생성하고 데이터 소스 API 키를 입력합니다.

```bash
cp .env.example .env
```

| 환경변수 | 필수 여부 | 용도 및 발급처 |
|---|---|---|
| `DART_API_KEY` | **필수** | 기업 개황, 재무제표, 최근 공시, 사업의 개요 조회 ([Open DART](https://opendart.fss.or.kr/) 무료 발급) |
| `ECOS_API_KEY` | 권장 | 한국은행 기준금리·환율·물가 등 거시지표 조회 ([한국은행 ECOS](https://ecos.bok.or.kr/) 무료 발급) |
| `NAVER_API_HUB_CLIENT_ID`<br>`NAVER_API_HUB_CLIENT_SECRET` | 선택 | 종목 뉴스 검색 (NCP NAVER API HUB 발급, 미설정 시 네이버 증권 뉴스로 자동 폴백) |
| `KRX_ID`<br>`KRX_PW` | 선택 | `pykrx` 투자자별 매매동향 조회용 KRX 정보데이터시스템 계정 (미설정·실패 시 네이버 증권 매매동향으로 자동 폴백) |

분석 모델, 추론 강도(`effort`), 타임아웃, 동시 실행 수(`TRADINGAGENTS_CLAUDE_CONCURRENCY`) 등 세부 설정은 `.env.example` 및 `tradingagents/default_config.py`를 참고하세요.

---

## 사용법

### 1. CLI

```bash
tradingagents          # 대화형 프롬프트 실행
python -m cli.main     # 모듈로 직접 실행
```

- **종목명 검색 (대화형 모드)**: 종목코드(`005930`, `0126Z0`)뿐 아니라 한글/영문 종목명(예: `삼성`)을 입력하면 매칭된 KRX 상장 종목 리스트에서 선택할 수 있습니다.
- **비대화형 실행**: 플래그를 지정하면 프롬프트 없이 바로 실행됩니다. (`--ticker` 플래그는 자동화 결정성을 위해 6자리 종목코드만 허용합니다.)
  ```bash
  tradingagents --ticker 005930 --date 2026-11-01 --analysts market,news,fundamentals --save --no-show
  ```
- **체크포인트 및 재개**: 중단된 분석을 마지막 완료 노드부터 이어서 실행합니다.
  ```bash
  tradingagents --checkpoint
  tradingagents --clear-checkpoints   # 저장된 체크포인트 초기화
  ```
- **백테스트**: 종목·날짜 그리드에 대해 과거 의사결정을 평가합니다.
  ```bash
  tradingagents backtest 005930,000660 --start 2026-10-01 --end 2026-11-01 --every 7
  ```
- **메모리 로그**: 실행 완료 시 `~/.tradingagents/memory/trading_memory.md`에 의사결정이 기록되며, 이후 실행에서 보유 기간 경과분의 실현 수익률 및 벤치마크(`069500` KODEX 200) 대비 알파가 자동 계산됩니다.

### 2. 로컬 웹 UI (Astro + FastAPI)

종목 검색, 분석 설정 및 실행, 실시간 진행 스트림(SSE), 저장된 리포트 열람 및 PDF 다운로드를 브라우저에서 사용할 수 있습니다. (Node.js `>=22.23.4` 필요)

**터미널 2개를 열어 백엔드와 프론트엔드를 각각 기동합니다:**

```bash
# [터미널 1] FastAPI 백엔드 (포트 8000)
source .venv/bin/activate
pip install -e ".[web]"                # 최초 1회
uvicorn api.main:app --reload --port 8000
```

```bash
# [터미널 2] Astro 프론트엔드 (포트 4321)
cd web
npm install                            # 최초 1회
npm run dev
```

- 브라우저에서 **http://localhost:4321** 에 접속해 종목을 검색하고 분석을 시작합니다.
- 완료된 리포트는 **http://localhost:4321/report** 에서 에이전트별 5단계 등급 요약과 함께 열람하거나 PDF로 내려받을 수 있습니다.
- 💡 **쿼터 절약 팁**: 처음 동작을 테스트할 때는 UI에서 `effort`를 `low`로 낮춰 실행하는 것을 권장합니다.
- **트러블슈팅**:
  - `"API 요청 실패"` 표시 시: 터미널 1의 `uvicorn` 프로세스가 실행 중인지 확인하세요.
  - 포트 8000 충돌 시: `uvicorn`을 `--port 8001`로 띄우고 `web/.env`에 `PUBLIC_API_BASE=http://localhost:8001`을 추가한 뒤 `npm run dev`를 재시작하세요.

### 3. Python API

```python
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "sonnet"     # 리서처·매니저·트레이더·디베이터 (sonnet / opus / haiku)
config["quick_think_llm"] = "haiku"     # 분석가
config["effort"] = "high"               # deep 티어 추론 강도: low / medium / high / xhigh / max
config["quick_effort"] = "medium"       # quick 티어 추론 강도
config["max_debate_rounds"] = 1

ta = TradingAgentsGraph(debug=True, config=config)

# 삼성전자(005930) 분석 실행 및 리포트 저장
state, decision = ta.propagate("005930", "2026-11-01")
print(decision)
ta.save_reports(state, "005930")
```

### 4. Docker 실행 (선택)

컨테이너 내부에 Node.js와 `@anthropic-ai/claude-code`가 사전 설치되어 있으며, 호스트의 `~/.claude/.credentials.json`을 읽기 전용으로 마운트해 인증을 공유합니다.

```bash
# 이미지 빌드
docker compose build

# 대화형 CLI 실행
docker compose run --rm tradingagents

# 비대화형 실행
docker compose run --rm tradingagents \
  --ticker 005930 --date 2026-11-03 --analysts market,news --save --no-show
```

---

## 테스트

```bash
# 유닛 테스트 (외부 네트워크 호출 없이 모킹으로 빠르게 실행)
pytest -q

# 통합 테스트 (실제 DART / ECOS / pykrx / 네이버 / Claude Code 호출 — 쿼터 소모 주의)
pytest -m integration -q
```

통합 테스트는 환경변수가 설정된 데이터 소스만 실행하고 미설정 항목은 자동으로 `skip` 처리합니다.

---

## 기반 프로젝트 및 인용 (Attribution & Citation)

본 프로젝트는 **[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)** 를 기반으로 제작된 한국 증시 전용 하드 포크입니다.

- **Upstream 저장소**: https://github.com/TauricResearch/TradingAgents
- **원 저작자**: Tauric Research (Yijia Xiao, Edward Sun, Di Luo, Wei Wang)
- **원 논문**: [TradingAgents: Multi-Agents LLM Financial Trading Framework (arXiv:2412.20138)](https://arxiv.org/abs/2412.20138)
- **라이선스**: Apache License 2.0 (`LICENSE` 참조)

학술적 목적으로 본 프로젝트를 참고하거나 활용하실 경우 원 저작자의 논문을 인용해 주세요:

```bibtex
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
