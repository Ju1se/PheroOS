#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

if [[ -f ".env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env.local"
  set +a
fi

if [[ -z "${ZAI_API_KEY:-}" && -n "${ZHIPU_API_KEY:-}" ]]; then
  export ZAI_API_KEY="${ZHIPU_API_KEY}"
fi

missing=()
if [[ -z "${ZAI_API_KEY:-}" ]]; then
  missing+=("ZAI_API_KEY or ZHIPU_API_KEY")
fi
if [[ -z "${MINIMAX_API_KEY:-}" ]]; then
  missing+=("MINIMAX_API_KEY")
fi

if (( ${#missing[@]} > 0 )); then
  printf 'Missing required environment variables: %s\n' "${missing[*]}" >&2
  printf 'Create .env.local with ZHIPU_API_KEY and MINIMAX_API_KEY, then rerun this script.\n' >&2
  exit 1
fi

export LITELLM_MASTER_KEY="${LITELLM_MASTER_KEY:-sk-local-master-key}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"

mkdir -p logs

pkill -f "litellm --config configs/litellm.yaml" 2>/dev/null || true
if command -v screen >/dev/null 2>&1; then
  screen -S litellm -X quit 2>/dev/null || true
fi
sleep 1

if command -v screen >/dev/null 2>&1; then
  screen -dmS litellm bash -lc "cd '$PWD' && exec .venv/bin/litellm --config configs/litellm.yaml --port '${LITELLM_PORT:-4000}' > logs/litellm.log 2>&1"
  printf 'LiteLLM restarted in screen session "litellm" on port %s. Log: logs/litellm.log\n' "${LITELLM_PORT:-4000}"
else
  nohup .venv/bin/litellm --config configs/litellm.yaml --port "${LITELLM_PORT:-4000}" > logs/litellm.log 2>&1 &
  printf 'LiteLLM restarted on port %s. Log: logs/litellm.log\n' "${LITELLM_PORT:-4000}"
fi
