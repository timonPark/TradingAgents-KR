#!/bin/sh
# Task 12c (#100): Docker 컨테이너 진입 스크립트.
#
# Claude Code CLI 는 OAuth credential 을 ``$HOME/.claude/.credentials.json`` 에서
# 읽습니다. 호스트의 credential 을 컨테이너에 읽기전용으로 공유하되 호스트
# ``~/.claude`` 디렉터리 전체는 **오염되지 않도록** 합니다:
#
# - 호스트는 ``~/.claude/.credentials.json`` 만 ``/claude-auth/.credentials.json``
#   읽기전용으로 마운트 (docker-compose.yml 참조).
# - 컨테이너는 ``HOME=/tmp/claude-home`` 를 쓰기 가능한 임시 디렉터리로 지정하고
#   그 아래 ``.claude/`` 를 생성한 뒤 credential 을 symlink.
# - Claude Code 가 세션/캐시/리프레시 상태를 ``/tmp/claude-home/.claude/`` 에 쓰므로
#   호스트는 영향받지 않고 컨테이너 종료 시 소실.
#
# 호스트에서 사전 ``claude login`` 이 완료되어야 합니다. credential 이 없으면
# 명확한 에러 메시지로 종료.
#
# code_artifact.md Task 12 의 "구현 전 검증" 사항 — HOME 재지정만으로 OAuth
# 리프레시 토큰 쓰기가 정상 작동한다는 가정 — 은 **검증 없이** 채택했습니다
# (사용자 승인). 작동 안 하면 docker-compose.yml 에서 ``~/.claude`` 전체를
# 읽기쓰기로 마운트하는 backoff 으로 전환하세요.
set -eu

CLAUDE_AUTH_SRC="${CLAUDE_AUTH_SRC:-/claude-auth/.credentials.json}"
CLAUDE_HOME="${HOME:-/tmp/claude-home}"
CLAUDE_DIR="$CLAUDE_HOME/.claude"
CLAUDE_CRED="$CLAUDE_DIR/.credentials.json"

# 호스트가 사전 로그인 안 되어 있으면 명확한 에러로 종료.
if [ ! -f "$CLAUDE_AUTH_SRC" ]; then
    cat >&2 <<EOF
[entrypoint] ERROR: Claude Code OAuth credential 을 찾을 수 없습니다:
    $CLAUDE_AUTH_SRC

호스트에서 사전에 \`claude login\` 을 완료해 \`~/.claude/.credentials.json\` 을
생성한 뒤 docker-compose.yml 의 볼륨 마운트가 올바른지 확인하세요.

Max/Pro 플랜 OAuth 로그인 가이드: https://docs.claude.com/en/docs/claude-code
EOF
    exit 1
fi

# $HOME/.claude 디렉터리를 쓰기 가능하게 생성. credential 은 symlink 로 연결
# (호스트 파일 변경 안 함).
mkdir -p "$CLAUDE_DIR"
if [ -L "$CLAUDE_CRED" ] || [ -e "$CLAUDE_CRED" ]; then
    rm -f "$CLAUDE_CRED"
fi
ln -s "$CLAUDE_AUTH_SRC" "$CLAUDE_CRED"

# 세션/캐시가 쓰여질 수 있도록 디렉터리 권한 확인.
chmod 700 "$CLAUDE_DIR" 2>/dev/null || true

# 원래 명령 실행 — Dockerfile 의 CMD (tradingagents) 또는 사용자가 docker run 에
# 추가로 전달한 명령.
exec "$@"
