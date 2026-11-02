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

## 커스터마이징 범위

TauricResearch 의 원본 프레임워크 대비 다음 레이어를 한국 환경으로 교체합니다.

| 영역 | upstream (원본) | TradingAgents-KR |
|---|---|---|
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

### 4. 한국 데이터 소스용 추가 라이브러리

```bash
pip install pykrx OpenDartReader finance-datareader
```

### 5. API 키 발급 및 `.env` 설정

```bash
# LLM (아래 중 하나 이상 필수)
export OPENAI_API_KEY=...          # OpenAI (GPT)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export GOOGLE_API_KEY=...          # Google (Gemini)

# 한국 데이터 소스
export DART_API_KEY=...            # 금융감독원 Open DART 인증키 (필수)
export ECOS_API_KEY=...            # 한국은행 ECOS API 인증키 (선택)
```

- **DART 인증키 발급**: [opendart.fss.or.kr](https://opendart.fss.or.kr/) 에서 무료 발급
- **ECOS 인증키 발급**: [ecos.bok.or.kr](https://ecos.bok.or.kr/) 에서 무료 발급

또는 `.env.example` 을 `.env` 로 복사하여 작성:

```bash
cp .env.example .env
```

---

## CLI 사용법

대화형 CLI 실행:

```bash
tradingagents          # 설치 후 사용 가능한 명령
python -m cli.main     # 또는 소스에서 직접 실행
```

종목코드, 분석 날짜, LLM 공급자, 리서치 깊이 등을 선택할 수 있는 화면이 나타납니다. 직전 실행의 응답이 기본값으로 복원되므로 Enter 만 누르면 그대로 재사용됩니다.

예시 (한국 종목):

```bash
tradingagents --ticker 005930 --date 2026-11-01 --analysts market,news,fundamentals --save
```

### 지원 티커 형식

TradingAgents-KR 은 한국거래소(KRX) 상장 종목을 기본 지원합니다.

- **KOSPI/KOSDAQ**: 6자리 숫자 코드 (예: `005930` 삼성전자, `035720` 카카오, `247540` 에코프로비엠)
- 미국 등 해외 종목은 upstream 의 Yahoo Finance 경로가 폴백으로 유지됩니다 (예: `AAPL`, `0700.HK`).

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
config["llm_provider"] = "anthropic"
config["deep_think_llm"] = "claude-opus-5-5"
config["quick_think_llm"] = "claude-haiku-5-0"
config["max_debate_rounds"] = 2
config["output_language"] = "Korean"

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
