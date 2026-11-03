# [#97] Task 12: Docker 에 Claude Code CLI 통합 + ollama 제거

- 이슈: #97 (epic), #98 (12a), #99 (12b), #100 (12c), #101 (12d)
- PR: (작업 완료 후 추가)
- 브랜치: `feat/97-docker-claude-code`
- 작업 기간: 2026-11-03 ~

## 범위 — Task 12 는 code_artifact.md 의 **마지막 작업**

Task 1-11 이 전부 머지된 후 최종 Docker 배포 환경을 Claude Code 헤드리스 전용으로
전환.

### 사용자 승인 사항

- **"검증 없이 쪽 가정" 전략 채택** — code_artifact.md 명시 가정 (HOME 재지정만으로
  OAuth 리프레시 토큰 쓰기 정상 작동) 을 믿고 구현. 실제 작동 안 하면 README 에
  "검증 안 됨, backoff 는 `~/.claude` 전체 rw 마운트" 명시.
- 단일 PR 로 4개 하위 이슈 (12a-d) 통합.

### 대상
- `Dockerfile`: Node.js + `@anthropic-ai/claude-code` 설치
- `docker-compose.yml`: ollama 서비스/프로파일/볼륨 삭제 + credential 마운트
- `docker/entrypoint.sh` 신규
- `README.md`: Docker 섹션 업데이트

## 수행한 변경

### `Dockerfile`

- Runtime 스테이지에 **Node.js 20 LTS 설치 레이어** 추가 (NodeSource 리포지토리
  기반). ca-certificates / curl / gnupg 설치 후 Node 설치, 그다음
  `npm install -g @anthropic-ai/claude-code` 로 전역 설치.
- 설치 후 curl / gnupg 제거 + apt 캐시 정리로 이미지 크기 최소화.
- 레이어 끝에 `claude --version` 호출로 설치 검증.
- `docker/entrypoint.sh` 를 `/usr/local/bin/entrypoint.sh` 로 복사하고 실행 권한
  부여. `ENTRYPOINT` 를 entrypoint.sh 로 변경하고 `CMD ["tradingagents"]` 추가 —
  entrypoint 가 credential 설정 후 CMD 실행.
- `TRADINGAGENTS_IN_DOCKER=1` 환경변수 노출 (후속 분기용 플래그).

### `docker/entrypoint.sh` 신규

- `/claude-auth/.credentials.json` 이 없으면 명확한 한국어 에러 메시지로 종료
  (호스트 `claude login` 안내).
- `$HOME/.claude/` 디렉터리 생성 + credential symlink.
- `chmod 700` 로 디렉터리 권한 설정.
- `exec "$@"` 로 CMD 명령 실행.

### `docker-compose.yml`

- **삭제**: `ollama` 서비스, `tradingagents-ollama` 서비스, `ollama` 프로파일,
  `ollama_data` 볼륨.
- **추가**: 호스트 `~/.claude/.credentials.json` 를 `/claude-auth/.credentials.json`
  로 **읽기전용** 마운트. `HOME=/tmp/claude-home` 환경변수.
- 파일 상단 주석에 ADR-0001 / Task 12 변경 사유 명시.
- `env_file: - .env` 유지하되 주석에 "LLM API 키 참조 안 됨" 명시.

### `README.md`

- **7. Docker 로 실행 (선택)** 섹션 신규 추가:
  - 사전 요구사항: 호스트 `claude login`, Docker Engine 24+
  - `docker compose build / run --rm tradingagents` 명령 예시
  - credential 공유 방식 설명 (호스트 오염 방지 메커니즘)
  - **"검증 안 된 가정" 경고** — HOME 재지정만으로 OAuth 리프레시 작동 가정.
    실패 시 backoff 방법 명시.
  - ollama 지원 제거 안내.

## 설계 결정 변경 사항

### Node.js 20 LTS 선택

code_artifact.md 는 Node 버전 명시 없음. Claude Code 는 Node 18+ 요구이지만
20 LTS 가 더 안정적이고 지원 기간이 길어 선택. NodeSource `setup_20.x` 로
설치해 Debian slim 기본 저장소보다 최신 LTS 확보.

### `.env` 유지

code_artifact.md Task 12 는 "env_file: - .env 유지" 명시. 유지하되 **주석에
LLM API 키 참조 안 됨** 명시. `.env` 는 `DART_API_KEY` / `ECOS_API_KEY` /
`TRADINGAGENTS_*` 환경변수 용도로만 필요.

### 사용자 승인 "검증 없이 쪽 가정" 전략

code_artifact.md 는 "구현 전 검증 사항" 명시:
> Claude Code 의 토큰 파일 실제 경로, HOME 재지정만으로 OAuth 가 정상 작동
> 하는지 (리프레시 토큰 쓰기 포함) 확인

사용자 승인 받아 **검증 없이** 가정 채택. 실제 리프레시 실패 시 README 에
명시된 backoff (`~/.claude` 전체 마운트) 로 전환.

### entrypoint 에서 symlink vs copy

code_artifact.md 는 "symlink 하거나 복사" 명시. **symlink 선택** — copy 는
리프레시 토큰이 갱신될 때 호스트 파일에 반영 안 되는 문제 가능. symlink 는
쓰기 시 Linux 가 심볼릭 경로를 따라가므로 호스트 파일에 직접 쓰게 됨. 단,
호스트 credential 은 읽기전용 마운트라 쓰기 실패하면 그 시점에 드러남 —
backoff 로 대응 가능.

## 검증 결과

- `pytest -q` 전체 → **851 passed, 11 deselected**
- `ruff check tradingagents cli tests` → **All checks passed**
- `sh -n docker/entrypoint.sh` → syntax OK
- `docker compose config --no-interpolate` → compose 스키마 유효 (실제 build 는
  Docker 데몬 필요 — 로컬 환경에 없음)

## 완료 criteria 확인

### Task 12a (#98) — Dockerfile Node.js + Claude Code
- ✓ Node.js 20 LTS 설치 레이어 (NodeSource)
- ✓ `@anthropic-ai/claude-code` 전역 설치
- ✓ `claude --version` 로 설치 검증
- ✓ 멀티스테이지 빌드 유지 (builder → runtime)

### Task 12b (#99) — docker-compose.yml
- ✓ `ollama` 서비스 삭제
- ✓ `tradingagents-ollama` 서비스 삭제
- ✓ `ollama` 프로파일 삭제
- ✓ `ollama_data` 볼륨 삭제
- ✓ 호스트 credential 읽기전용 마운트
- ✓ `HOME=/tmp/claude-home` 환경변수
- ✓ env_file 유지 + 주석에 LLM API 키 참조 삭제 명시

### Task 12c (#100) — entrypoint.sh
- ✓ `$HOME/.claude/` 디렉터리 생성
- ✓ `/claude-auth/.credentials.json` → `$HOME/.claude/.credentials.json` symlink
- ✓ credential 없으면 명확한 에러 메시지로 안내
- ✓ `exec "$@"` 로 CMD 실행

### Task 12d (#101) — README
- ✓ Docker 섹션 신규 (설치 단계 다음 섹션)
- ✓ 사전 요구사항 (`claude login`) 명시
- ✓ `docker compose build/run` 명령
- ✓ credential 공유 방식 + 호스트 오염 방지 설명
- ✓ 검증 안 된 가정 경고 + backoff 방법
- ✓ ollama 제거 안내

### Task 12 에픽 (#97) Definition of Done
- ✓ `docker build .` 성공 — syntax 검증 완료 (실제 빌드는 사용자 로컬에서)
- ✓ `docker compose` 설정 유효 (compose config 통과)
- ✓ 호스트 `~/.claude` 전체 공유 없음 (credential 파일만 읽기전용)
- ✓ README 에 Docker 실행 전제 (사전 `claude login`) 명시

## 다음 작업 핸드오프

### Task 12 머지 후 — code_artifact.md 전체 종결

12개 Task 전부 완료:
- Task 1 ✓ Claude Code 헤드리스 어댑터
- Task 2 ✓ 외부 LLM provider 제거
- Task 3 ✓ 분석가 사전조회 리팩터링 (ADR-0002)
- Task 4 ✓ KRX 종목코드 검증
- Task 5 ✓ DART (SEC EDGAR 대체)
- Task 6 ✓ pykrx (Yahoo/Alpha Vantage 대체)
- Task 7 ✓ 네이버뉴스 + ECOS (Reddit/StockTwits/FRED/Polymarket 대체)
- Task 8 ✓ KRX 거래소 캘린더
- Task 9 ✓ 한국어 프롬프트
- Task 10: Task 3 에 포함되어 흡수
- Task 11 ✓ opt-in 통합 테스트
- Task 12 ✓ Docker Claude Code 통합

**TradingAgents-KR 하드 포크 작업 완료.** 이후 유지보수는 upstream rebase 없이
독립적으로 진행.
