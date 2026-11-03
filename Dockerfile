# Builder: Python 패키지 설치용 가상 환경
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir .


# Runtime: Python + Node.js + Claude Code CLI
FROM python:3.13-slim

# TRADINGAGENTS_IN_DOCKER lets an update notice name the rebuild command.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADINGAGENTS_IN_DOCKER=1

# Task 12a (#98): Claude Code CLI 는 Node.js 20+ 를 요구. NodeSource 리포지토리로
# Debian slim 기본 저장소보다 최신 LTS 를 설치. ca-certificates / curl 는 NodeSource
# setup 스크립트가 요구. gnupg 는 setup 스크립트의 서명 키 검증용.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @anthropic-ai/claude-code \
 && apt-get purge -y curl gnupg \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/* \
 && claude --version

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home appuser \
 && install -d -m 0755 -o appuser -g appuser /home/appuser/.tradingagents

# Task 12c (#100): entrypoint 스크립트 — OAuth credential 을 HOME 아래로 연결 후
# 명령 실행. docker-compose 가 호스트 credential 을 /claude-auth 아래 읽기전용으로
# 마운트하면 entrypoint 가 $HOME/.claude 로 symlink.
COPY --chown=root:root docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER appuser
WORKDIR /home/appuser/app

COPY --from=builder --chown=appuser:appuser /build .

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["tradingagents"]
