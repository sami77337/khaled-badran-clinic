#!/usr/bin/env bash
set -u

STRICT=0
JSON_OUTPUT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict)
      STRICT=1
      shift
      ;;
    --json)
      JSON_OUTPUT=1
      shift
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

find_repo_root() {
  local current
  current="$(pwd)"
  while true; do
    if [[ -f "$current/manage.py" && -d "$current/.git" ]]; then
      printf '%s\n' "$current"
      return 0
    fi
    local parent
    parent="$(dirname "$current")"
    if [[ -z "$parent" || "$parent" == "$current" ]]; then
      printf 'Could not locate repository root containing manage.py and .git.\n' >&2
      return 1
    fi
    current="$parent"
  done
}

redact_output() {
  sed -E \
    -e 's/(DJANGO_SECRET_KEY|SECRET_KEY|DATABASE_URL|CACHE_URL|PASSWORD|TOKEN|DSN)[[:space:]]*=[^[:space:]]+/\1=<redacted>/Ig' \
    -e 's#(postgres|postgresql|redis|rediss)://[^[:space:]]+#<redacted-url>#Ig'
}

run_safe() {
  printf '\n$'
  printf ' %q' "$@"
  printf '\n'

  local output status
  output="$("$@" 2>&1)"
  status=$?
  printf '%s\n' "$output" | redact_output
  if [[ $status -ne 0 ]]; then
    printf 'Command failed with exit code %s:' "$status" >&2
    printf ' %q' "$@" >&2
    printf '\n' >&2
    return "$status"
  fi
}

check_env_contract() {
  local required missing name value
  required=(
    DJANGO_SETTINGS_MODULE
    DJANGO_SECRET_KEY
    DJANGO_DEBUG
    DJANGO_ALLOWED_HOSTS
    DJANGO_CSRF_TRUSTED_ORIGINS
    DATABASE_URL
    CACHE_URL
    DJANGO_CACHE_KEY_PREFIX
  )
  missing=()

  printf '\nStaging environment contract presence check; values are not printed.\n'
  for name in "${required[@]}"; do
    value="${!name-}"
    if [[ -z "$value" ]]; then
      missing+=("$name")
      printf '%s: missing\n' "$name"
    else
      printf '%s: present\n' "$name"
    fi
  done

  if [[ -n "${DJANGO_DEBUG-}" && "${DJANGO_DEBUG,,}" != "false" ]]; then
    missing+=("DJANGO_DEBUG=false")
    printf 'DJANGO_DEBUG: not false\n'
  fi

  if [[ $STRICT -eq 1 && ${#missing[@]} -gt 0 ]]; then
    printf 'Strict staging validation failed environment contract presence checks: %s\n' "${missing[*]}" >&2
    return 1
  fi
}

main() {
  local repo_root
  repo_root="$(find_repo_root)" || return 1
  cd "$repo_root" || return 1

  printf 'Restricted staging environment validation for Dr. Khaled Badran Clinic\n'
  printf 'Repository root: %s\n' "$repo_root"
  printf 'Strict mode: %s\n' "$STRICT"
  printf 'JSON command output mode: %s\n' "$JSON_OUTPUT"

  run_safe git branch --show-current || return 1
  run_safe git rev-parse HEAD || return 1
  check_env_contract || return 1
  run_safe python manage.py makemigrations --check --dry-run || return 1
  run_safe python manage.py migrate --check || return 1
  run_safe python manage.py check || return 1
  run_safe python manage.py check --deploy || return 1

  local smoke_args report_args
  smoke_args=(python manage.py deployment_smoke)
  report_args=(python manage.py project_status_report)
  if [[ $STRICT -eq 1 ]]; then
    smoke_args+=(--strict)
  fi
  if [[ $JSON_OUTPUT -eq 1 ]]; then
    smoke_args+=(--json)
    report_args+=(--json)
  fi
  run_safe "${smoke_args[@]}" || return 1
  run_safe "${report_args[@]}" || return 1
  run_safe python manage.py test || return 1

  printf '\nRestricted staging environment validation completed.\n'
}

main
