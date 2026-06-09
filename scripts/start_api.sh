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

export LITELLM_BASE_URL="${LITELLM_BASE_URL:-http://127.0.0.1:4000/v1}"
export LITELLM_MASTER_KEY="${LITELLM_MASTER_KEY:-sk-local-master-key}"
export LITELLM_TIMEOUT="${LITELLM_TIMEOUT:-2000}"
export LITELLM_CLIENT_MAX_RETRIES="${LITELLM_CLIENT_MAX_RETRIES:-3}"
export LITELLM_RETRY_BASE_SECONDS="${LITELLM_RETRY_BASE_SECONDS:-2}"
export GLM_MAX_CONCURRENCY="${GLM_MAX_CONCURRENCY:-2}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"
export WEB_PROXY_URL="${WEB_PROXY_URL:-}"
export WEB_PROXY_REQUIRED="${WEB_PROXY_REQUIRED:-false}"
export WEB_SEARCH_ENGLISH_ONLY="${WEB_SEARCH_ENGLISH_ONLY:-false}"
export WEB_SEARCH_LANGUAGE="${WEB_SEARCH_LANGUAGE:-}"
export WEB_SEARCH_COUNTRY="${WEB_SEARCH_COUNTRY:-}"
export PROVIDER_WEB_SEARCH_ENABLED="${PROVIDER_WEB_SEARCH_ENABLED:-true}"
export PROVIDER_WEB_SEARCH_MODEL="${PROVIDER_WEB_SEARCH_MODEL:-glm-5.1-standard}"
export PROVIDER_WEB_SEARCH_ENGINE="${PROVIDER_WEB_SEARCH_ENGINE:-search-prime}"
export PROVIDER_WEB_SEARCH_RECENCY_FILTER="${PROVIDER_WEB_SEARCH_RECENCY_FILTER:-noLimit}"
export PROVIDER_WEB_SEARCH_CONTENT_SIZE="${PROVIDER_WEB_SEARCH_CONTENT_SIZE:-medium}"
export PROVIDER_WEB_SEARCH_MAX_RESULTS="${PROVIDER_WEB_SEARCH_MAX_RESULTS:-5}"
export CIO_AGENT_MODEL="${CIO_AGENT_MODEL:-glm-5.1}"
export DATA_AUDITOR_AGENT_MODEL="${DATA_AUDITOR_AGENT_MODEL:-glm-5.1}"
export FUNDAMENTAL_ANALYST_AGENT_MODEL="${FUNDAMENTAL_ANALYST_AGENT_MODEL:-glm-5.1}"
export QUANT_RESEARCH_AGENT_MODEL="${QUANT_RESEARCH_AGENT_MODEL:-glm-5.1}"
export INDUSTRY_STRATEGY_AGENT_MODEL="${INDUSTRY_STRATEGY_AGENT_MODEL:-glm-5.1}"
export MARKET_EXECUTION_AGENT_MODEL="${MARKET_EXECUTION_AGENT_MODEL:-minimax-m2.7}"
export RISK_MANAGER_AGENT_MODEL="${RISK_MANAGER_AGENT_MODEL:-glm-5.1}"
export RED_TEAM_AGENT_MODEL="${RED_TEAM_AGENT_MODEL:-minimax-m2.7}"
export COMMITTEE_MEMBER_FALLBACK_MODEL="${COMMITTEE_MEMBER_FALLBACK_MODEL:-minimax-m2.7}"
export INVESTMENT_COMMITTEE_FALLBACK_MODEL="${INVESTMENT_COMMITTEE_FALLBACK_MODEL:-minimax-m2.7}"

exec .venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 \
  --port "${API_PORT:-8000}" \
  --reload \
  --reload-dir app \
  --reload-dir runtime \
  --reload-dir tools \
  --reload-dir skills \
  --reload-dir static
