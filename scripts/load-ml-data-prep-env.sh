#!/usr/bin/env bash

# This script must be sourced, not executed.
#
# Usage:
#
#   source scripts/load-ml-data-prep-env.sh
#
# or:
#
#   source scripts/load-ml-data-prep-env.sh .env.ml
#
# It loads stable ML data-prep environment variables from .env.ml.
# It intentionally does not define ML_PREP_START_UTC or ML_PREP_END_UTC.

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "ERROR: this script must be sourced, not executed."
  echo
  echo "Use:"
  echo "  source scripts/load-ml-data-prep-env.sh"
  exit 2
fi

ML_ENV_FILE="${1:-.env.ml}"

if [[ ! -f "${ML_ENV_FILE}" ]]; then
  echo "ERROR: ML env file not found: ${ML_ENV_FILE}"
  echo
  echo "Create it from the example:"
  echo "  cp .env.ml.example .env.ml"
  return 2
fi

# Export all variables defined by the env file.
set -a
# shellcheck disable=SC1090
source "${ML_ENV_FILE}"
set +a

# Safety: keep dataset range explicitly per-run.
unset ML_PREP_START_UTC
unset ML_PREP_END_UTC

echo "Loaded ML data-prep environment from ${ML_ENV_FILE}"
echo "ML_PREP_START_UTC and ML_PREP_END_UTC were intentionally left unset."
echo
echo "Run with:"
echo "  ML_PREP_START_UTC=2024-01-01T00:00:00Z \\"
echo "  ML_PREP_END_UTC=2024-06-01T00:00:00Z \\"
echo "  python -m app.modules.ml_data_prep.job"
