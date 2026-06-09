#!/usr/bin/env bash
set -euo pipefail

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

export LITELLM_MASTER_KEY="${LITELLM_MASTER_KEY:-sk-local-master-key}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"

exec .venv/bin/litellm --config configs/litellm.yaml --port "${LITELLM_PORT:-4000}"
