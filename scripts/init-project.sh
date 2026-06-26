#!/usr/bin/env bash
# ============================================================================
# FastAPI Template — Project Initialization Script
# ============================================================================
# Usage:
#   bash scripts/init-project.sh                    # interactive mode
#   bash scripts/init-project.sh my-awesome-api     # non-interactive mode
#
# Run this ONCE right after creating a new project from the GitHub template.
# It interactively collects your project details and replaces ALL hardcoded
# template defaults (project name, description, database name, registry, etc.)
#
# The template repo keeps working defaults so it's immediately runnable;
# this script handles the one-time migration to YOUR project identity.
# ============================================================================

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Guard: run from project root ────────────────────────────────────────
cd "$(dirname "$0")/.."
if [ ! -f "pyproject.toml" ] || [ ! -f "scripts/init-project.sh" ]; then
  err "Please run this script from the project root directory."
  err "  cd /path/to/your-project && bash scripts/init-project.sh"
  exit 1
fi

# ── Helper: prompt with default (works with pipes and CI) ───────────────
prompt_with_default() {
  local var_name="$1" prompt_text="$2" default_val="$3"
  local input
  if [ -n "${NON_INTERACTIVE:-}" ]; then
    printf -v "$var_name" "%s" "$default_val"
    return
  fi
  # Use /dev/tty if available, fall back to stdin
  if [ -t 0 ]; then
    read -r -p "${prompt_text} [${default_val}]: " input
  else
    # Non-interactive (piped): silent, take default
    printf -v "$var_name" "%s" "$default_val"
    return
  fi
  printf -v "$var_name" "%s" "${input:-$default_val}"
}

# ── Validate kebab-case ─────────────────────────────────────────────────
is_kebab_case() {
  [[ "$1" =~ ^[a-z][a-z0-9]*(-[a-z0-9]+)*$ ]]
}

# ── 0. Non-interactive mode: first arg = project name (kebab-case) ──────
if [ $# -ge 1 ]; then
  NON_INTERACTIVE=1
  PROJECT_NAME="$1"
  if ! is_kebab_case "$PROJECT_NAME"; then
    err "Invalid project name: '$PROJECT_NAME'"
    err "Use kebab-case: lowercase letters, digits, hyphens."
    exit 1
  fi
  info "Non-interactive mode: ${PROJECT_NAME}"
fi

# ── 1. Greeting ─────────────────────────────────────────────────────────
echo ""
info "============================================================"
info "  FastAPI Template — Project Initializer"
info "============================================================"
echo ""

# ── 2. Collect values (or skip in non-interactive mode) ─────────────────
if [ -z "${NON_INTERACTIVE:-}" ]; then
  # ── 2a. Project name (kebab-case) ───────────────────────────────────
  while true; do
    prompt_with_default PROJECT_NAME "Project name (kebab-case)" "my-awesome-api"
    if is_kebab_case "$PROJECT_NAME"; then
      break
    fi
    err "Invalid. Use kebab-case: lowercase letters, digits, hyphens."
    echo ""
  done

  # ── 2b. Description ─────────────────────────────────────────────────
  DEFAULT_DESCRIPTION="${PROJECT_NAME} - FastAPI project"
  prompt_with_default PROJECT_DESCRIPTION "Description" "$DEFAULT_DESCRIPTION"

  # ── 2c. Database name ───────────────────────────────────────────────
  DEFAULT_DB_NAME="${PROJECT_NAME//-/_}_dev"
  prompt_with_default DB_NAME "Database name" "$DEFAULT_DB_NAME"

  # ── 2d. Registry URL ────────────────────────────────────────────────
  prompt_with_default REGISTRY_URL "Docker registry" "registry.example.com"
else
  # Non-interactive: auto-derive from PROJECT_NAME
  PROJECT_DESCRIPTION="${PROJECT_NAME} - FastAPI project"
  DB_NAME="${PROJECT_NAME//-/_}_dev"
  REGISTRY_URL="registry.example.com"
fi

SAFE_NAME="${PROJECT_NAME//-/_}"
# Title case: "my-awesome-api" -> "My Awesome Api"
TITLE_NAME=$(echo "$SAFE_NAME" | sed 's/_/ /g' | sed 's/\b\(.\)/\u\1/g')
# Also handle the kebab case version: "my-awesome-api" -> "My Awesome Api"
TITLE_NAME=$(echo "$PROJECT_NAME" | sed 's/-/ /g' | sed 's/\b\(.\)/\u\1/g')
UPPER_NAME=$(echo "$SAFE_NAME" | tr '[:lower:]' '[:upper:]')

# ── 3. Summary ──────────────────────────────────────────────────────────
echo ""
info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Project name     : $PROJECT_NAME"
info "Python package   : $SAFE_NAME"
info "Display title    : $TITLE_NAME"
info "Description      : $PROJECT_DESCRIPTION"
info "Database name    : $DB_NAME"
info "Registry URL     : $REGISTRY_URL"
info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 4. Feature selection ─────────────────────────────────────────────
# ── 4. Feature selection ─────────────────────────────────────────────
info "Feature selection (Y/n — press Enter for Yes, type n for No):"
echo ""

prompt_yn() {
  local var_name="$1" prompt_text="$2" default_val="${3:-y}"
  local env_var_name="${var_name}_OVERRIDE"
  # In non-interactive mode, check for env var (e.g. FEAT_POSTGRES=n)
  if [ -n "${NON_INTERACTIVE:-}" ]; then
    local env_val
    env_val="$(eval echo "\${${var_name}:-}")"
    if [ -n "$env_val" ]; then
      printf -v "$var_name" "%s" "$env_val"
    else
      printf -v "$var_name" "%s" "$default_val"
    fi
    return
  fi
  if [ -t 0 ]; then
    read -r -p "${prompt_text} [${default_val}]: " input
  else
    printf -v "$var_name" "%s" "$default_val"
    return
  fi
  input="${input:-$default_val}"
  case "$input" in
    [Yy]*) printf -v "$var_name" "y" ;;
    [Nn]*) printf -v "$var_name" "n" ;;
    *)     printf -v "$var_name" "$default_val" ;;
  esac
}

prompt_yn FEAT_POSTGRES "  PostgreSQL database + ORM" "y"
prompt_yn FEAT_REDIS    "  Redis"                    "y"
prompt_yn FEAT_AUTH     "  JWT auth + user module"   "y"
prompt_yn FEAT_RATELIMIT "  Rate limiting"            "y"

# Validate dependencies
if [ "$FEAT_AUTH" = "y" ] && [ "$FEAT_POSTGRES" = "n" ]; then
  warn "Auth requires PostgreSQL — disabling auth."
  FEAT_AUTH="n"
fi
if [ "$FEAT_AUTH" = "y" ] && [ "$FEAT_REDIS" = "n" ]; then
  warn "Auth with Redis disabled: token blacklist disabled, JWT validation only."
fi

echo ""
info "Features: PostgreSQL=$FEAT_POSTGRES Redis=$FEAT_REDIS Auth=$FEAT_AUTH RateLimit=$FEAT_RATELIMIT"
echo ""

# ── 4b. Build replacement list ──────────────────────────────────────────
# Three parallel arrays to avoid delimiter issues (values may contain colons)
FILES=()
OLDS=()
NEWS=()

add() {
  FILES+=("$1")
  OLDS+=("$2")
  NEWS+=("$3")
}

# --- pyproject.toml ---
add "pyproject.toml" 'name = "fastapi-template"'         'name = "'"${PROJECT_NAME}"'"'
add "pyproject.toml" 'description = "FastAPI 项目模板"'  'description = "'"${PROJECT_DESCRIPTION}"'"'
add "pyproject.toml" 'FastAPI 项目模板'                   "${PROJECT_DESCRIPTION}"

# --- README.md ---
add "README.md" "fastapi-template"   "${PROJECT_NAME}"
add "README.md" "FastAPI 项目模板"   "${PROJECT_DESCRIPTION}"

# --- Makefile ---
add "Makefile" "# fastapi-template Makefile"  "# ${PROJECT_NAME} Makefile"
add "Makefile" "IMAGE_NAME ?= fastapi-template"  "IMAGE_NAME ?= ${PROJECT_NAME}"
add "Makefile" "REGISTRY ?= registry.example.com" "REGISTRY ?= ${REGISTRY_URL}"

# --- src/.example.env ---
add "src/.example.env" "APP_TITLE=fastapi-template"  "APP_TITLE=${PROJECT_NAME}"
add "src/.example.env" "FASTAPI_TEMPLATE"             "${UPPER_NAME}"

# --- src/.env (if exists) ---
if [ -f src/.env ]; then
  add "src/.env" "APP_TITLE=fastapi-template"  "APP_TITLE=${PROJECT_NAME}"
  add "src/.env" "FASTAPI_TEMPLATE"             "${UPPER_NAME}"
fi

# --- pyproject.toml: markers description ---
add "pyproject.toml" "require MySQL and Redis"           "require PostgreSQL and Redis"

# --- src/app/core/settings/config.py ---
add "src/app/core/settings/config.py" 'Field("fastapi-template"'  'Field("'"${PROJECT_NAME}"'"'

# --- docker/docker-compose.yml (production) ---
add "docker/docker-compose.yml" "name: fastapi-template"              "name: ${PROJECT_NAME}"
add "docker/docker-compose.yml" "/fastapi-template"                   "/${PROJECT_NAME}"
add "docker/docker-compose.yml" "fastapi-template-net"                "${PROJECT_NAME}-net"
add "docker/docker-compose.yml" "fastapi-template-postgres-data"      "${PROJECT_NAME}-postgres-data"
add "docker/docker-compose.yml" "fastapi-template-postgres"           "${PROJECT_NAME}-postgres"
add "docker/docker-compose.yml" "fastapi-template-redis"              "${PROJECT_NAME}-redis"
add "docker/docker-compose.yml" "registry.example.com"                "${REGISTRY_URL}"
add "docker/docker-compose.yml" "devdb"                               "${DB_NAME}"

# --- docker/docker-compose.dev.yml (development) ---
add "docker/docker-compose.dev.yml" "name: fastapi-template-dev"          "name: ${PROJECT_NAME}-dev"
add "docker/docker-compose.dev.yml" "dev-fastapi-template"                "dev-${PROJECT_NAME}"
add "docker/docker-compose.dev.yml" "fastapi-template-dev-net"            "${PROJECT_NAME}-dev-net"
add "docker/docker-compose.dev.yml" "fastapi-template-venv"               "${PROJECT_NAME}-venv"
add "docker/docker-compose.dev.yml" "dev-fastapi-template-postgres"       "dev-${PROJECT_NAME}-postgres"
add "docker/docker-compose.dev.yml" "dev-fastapi-template-redis"          "dev-${PROJECT_NAME}-redis"
add "docker/docker-compose.dev.yml" "dev-fastapi-template-postgres-data"  "dev-${PROJECT_NAME}-postgres-data"
add "docker/docker-compose.dev.yml" "devdb"                               "${DB_NAME}"

# ── 5. Execute replacements ─────────────────────────────────────────────
info "Patching files …"
echo ""

TOTAL=0
for i in "${!FILES[@]}"; do
  FILE="${FILES[$i]}"
  OLD="${OLDS[$i]}"
  NEW="${NEWS[$i]}"

  if [ ! -f "$FILE" ]; then
    continue
  fi

  # Escape for literal sed match (escape /, &, and backslash)
  OLD_ESC=$(printf '%s\n' "$OLD" | sed 's:[/\&]:\\&:g')
  NEW_ESC=$(printf '%s\n' "$NEW" | sed 's:[/\&]:\\&:g')

  # Count matches before replacement
  MATCHES=$(grep -c -- "$OLD" "$FILE" 2>/dev/null || true)

  if [ "$MATCHES" -gt 0 ]; then
    sed -i "s/$OLD_ESC/$NEW_ESC/g" "$FILE"
    ok "${FILE}: replaced ${MATCHES}x '${OLD}'"
    TOTAL=$((TOTAL + MATCHES))
  fi
done

echo ""
if [ "$TOTAL" -eq 0 ]; then
  warn "No replacements were made — everything already patched?"
  echo ""
  exit 0
fi

ok "Done! ${TOTAL} replacements across ${#FILES[@]} files."

# ── 6. Feature cleanup: remove disabled features ──────────────────────
echo ""
FEATURE_CLEANUP=false

# ── 6a. PostgreSQL ──────────────────────────────────────────────────────
if [ "$FEAT_POSTGRES" = "n" ]; then
  FEATURE_CLEANUP=true
  info "Removing PostgreSQL and database layer …"

  # Transform main.py: remove lifespan + DB imports
  python3 << 'PYEOF'
import re
import os

def remove_db_from_main():
    DOTALL = re.DOTALL
    path = 'src/app/main.py'
    with open(path) as f:
        content = f.read()

    content = re.sub(r'^from app\.db\.session.*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^from collections\.abc import AsyncGenerator\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^from contextlib import asynccontextmanager\n', '', content, flags=re.MULTILINE)

    # Remove lifespan function (including emoji in log message)
    content = re.sub(
        r'\n@asynccontextmanager\nasync def lifespan.*?:\n    await init_db\(\)\n    logger\.info\(.*?\)\n    yield\n    await close_db\(\)\n',
        '',
        content,
    )

    # Remove lifespan=lifespan from FastAPI() call (with trailing comma and various indent)
    content = re.sub(r'\n\s*lifespan=lifespan,?', '', content)

    with open(path, 'w') as f:
        f.write(content)

def simplify_health():
    path = 'src/app/api/endpoints/health.py'
    with open(path) as f:
        content = f.read()

    content = re.sub(r'^from sqlalchemy.*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'^from app\.db\.session.*\n', '', content, flags=re.MULTILINE)
    content = content.replace('from fastapi import APIRouter, Depends', 'from fastapi import APIRouter')
    content = content.replace('    session: AsyncSession = Depends(get_session),\n', '')
    content = re.sub(
        r'    db_ok = True\n    try:\n        await session\.execute.*?\n    except Exception:\n        db_ok = False\n\n',
        '',
        content,
    )
    content = content.replace(
        '            "db": "ok" if db_ok else "ng",\n',
        '',
    )

    with open(path, 'w') as f:
        f.write(content)

def remove_db_settings():
    path = 'src/app/core/settings/config.py'
    with open(path) as f:
        content = f.read()

    content = re.sub(
        r'    db_url: str = Field\(\n.*?description=.*?\n    \)\n',
        '',
        content,
        flags=re.DOTALL,
    )

    with open(path, 'w') as f:
        f.write(content)

def remove_pyproject_db_deps():
    path = 'pyproject.toml'
    with open(path) as f:
        content = f.read()

    for dep in ['"asyncpg>=', '"sqlmodel>=', '"alembic>=', '"sqlalchemy>=']:
        content = re.sub(r'^  ' + re.escape(dep) + r'.*\n', '', content, flags=re.MULTILINE)

    with open(path, 'w') as f:
        f.write(content)

def strip_docker_db():
    """Remove postgres service, volumes, and depends_on from compose files."""
    import re
    for fpath in ['docker/docker-compose.yml', 'docker/docker-compose.dev.yml']:
        with open(fpath) as f:
            content = f.read()

        # Remove postgres service block
        content = re.sub(r'\n  postgres:\n(?:    .+\n?)*', '\n', content)
        # Remove postgres_data volume refs (including name: sub-line)
        content = re.sub(r'\n  (?:dev_)?postgres_data:\n(?:    .+\n?)?', '\n', content)
        # Remove DB_URL and REDIS_URL env lines
        content = re.sub(r'\n      DB_URL:.*', '', content)
        content = re.sub(r'\n      REDIS_URL:.*', '', content)
        # Remove depends_on blocks mentioning postgres/redis
        content = re.sub(r'\n    depends_on:\n(?:      .+\n(?:        .+\n)?)*', '\n', content)
        # Clean up blank lines
        content = re.sub(r'\n{3,}', '\n\n', content)

        with open(fpath, 'w') as f:
            f.write(content)

remove_db_from_main()
simplify_health()
remove_db_settings()
remove_pyproject_db_deps()
strip_docker_db()
PYEOF

  # Delete DB-related files
  rm -rf src/app/db src/app/models src/app/crud alembic alembic.ini

  ok "PostgreSQL layer removed."
fi

# ── 6b. Redis ───────────────────────────────────────────────────────────
if [ "$FEAT_REDIS" = "n" ]; then
  FEATURE_CLEANUP=true
  info "Removing Redis …"

  # Remove redis_url from settings
  sed -i '/redis_url/d' src/app/core/settings/config.py

  # Remove redis dependency from pyproject.toml
  sed -i '/"redis>=/d' pyproject.toml

  # If auth stays, strip RedisTokenService calls from auth
  if [ "$FEAT_AUTH" = "y" ]; then
    python3 << 'PYEOF'
def strip_redis_from_auth():
    path = 'src/app/api/deps/auth.py'
    with open(path) as f:
        content = f.read()

    content = re.sub(r'^from app\.infrastructure\.redis.*\n', '', content, flags=re.MULTILINE)
    # Remove RedisTokenService usage: from redis_service = RedisTokenService() to is_valid check
    content = re.sub(
        r'    redis_service = RedisTokenService\(\)\n    is_valid = await redis_service\.validate_token.*?\n    if not is_valid:\n        raise ApiException.*?\n\n',
        '',
        content,
    )

    with open(path, 'w') as f:
        f.write(content)

def strip_redis_from_user_service():
    path = 'src/app/services/user_service.py'
    with open(path) as f:
        content = f.read()

    content = re.sub(r'^from app\.infrastructure\.redis.*\n', '', content, flags=re.MULTILINE)
    # Remove store_token call
    content = re.sub(
        r'    redis_service = RedisTokenService\(\)\n        await redis_service\.store_token.*?\n\n',
        '',
        content,
    )

    with open(path, 'w') as f:
        f.write(content)

import re
strip_redis_from_auth()
strip_redis_from_user_service()
PYEOF
  fi

  # Delete Redis files
  rm -rf src/app/infrastructure/redis

  # Remove Redis from docker-compose
  sed -i '/^  redis:/,/^  [a-z]/{ /^  [a-z]/!d; }' docker/docker-compose.yml 2>/dev/null || true
  sed -i '/^  redis:/,/^  [a-z]/{ /^  [a-z]/!d; }' docker/docker-compose.dev.yml 2>/dev/null || true
  sed -i '/^  redis:/d' docker/docker-compose.dev.yml docker/docker-compose.yml 2>/dev/null || true
  sed -i '/\bcondition: service_healthy/d' docker/docker-compose.dev.yml docker/docker-compose.yml 2>/dev/null || true

  ok "Redis removed."
fi

# ── 6c. Rate limiting ───────────────────────────────────────────────────
if [ "$FEAT_RATELIMIT" = "n" ]; then
  FEATURE_CLEANUP=true
  info "Removing rate limiting …"

  # Remove from main.py
  sed -i '/add_rate_limit_middleware/d' src/app/main.py
  sed -i '/^    add_rate_limit_middleware/d' src/app/main.py

  # Remove from middlewares/__init__.py
  sed -i '/rate_limit/d' src/app/middlewares/__init__.py

  # Remove RateLimitExceeded handler from error_handler.py
  python3 << 'PYEOF'
import re

def strip_rate_limit_from_errors():
    path = 'src/app/middlewares/error_handler.py'
    with open(path) as f:
        lines = f.readlines()

    result = []
    skip = False
    for line in lines:
        if '@application.exception_handler(RateLimitExceeded)' in line:
            skip = True
            continue
        if skip:
            # Next handler decorator → stop skipping
            stripped = line.lstrip()
            if stripped.startswith('@application.exception_handler'):
                skip = False
            else:
                continue  # Still inside the block we're removing
        result.append(line)

    content = ''.join(result)
    content = re.sub(r'^from slowapi.*\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'\n{3,}', '\n\n', content)

    with open(path, 'w') as f:
        f.write(content)

def remove_rate_limit_settings():
    path = 'src/app/core/settings/config.py'
    with open(path) as f:
        content = f.read()
    content = re.sub(r'^    rate_limit_.*\n', '', content, flags=re.MULTILINE)
    with open(path, 'w') as f:
        f.write(content)

def remove_slowapi_dep():
    path = 'pyproject.toml'
    with open(path) as f:
        content = f.read()
    content = re.sub(r'^  "slowapi>=.*\n', '', content, flags=re.MULTILINE)
    with open(path, 'w') as f:
        f.write(content)

strip_rate_limit_from_errors()
remove_rate_limit_settings()
remove_slowapi_dep()
PYEOF

  # Delete rate limit files
  rm -rf src/app/infrastructure/rate_limit src/app/middlewares/rate_limit.py src/app/utils/rate_limit.py

  ok "Rate limiting removed."
fi

# ── 6d. Auth + user module ──────────────────────────────────────────────
if [ "$FEAT_AUTH" = "n" ]; then
  FEATURE_CLEANUP=true
  info "Removing auth and user module …"

  # Remove from routes.py
  sed -i 's/from app.api.endpoints import health, user/from app.api.endpoints import health/' src/app/api/routes.py
  sed -i '/api_router.include_router(user\.router/d' src/app/api/routes.py

  # Remove JWT/python-jose deps from pyproject.toml
  sed -i '/"python-jose/d' pyproject.toml
  sed -i '/"bcrypt>/d' pyproject.toml

  # Remove JWT fields from settings
  python3 << 'PYEOF'
import re
path = 'src/app/core/settings/config.py'
with open(path) as f:
    content = f.read()
content = re.sub(r'^    jwt_.*\n', '', content, flags=re.MULTILINE)
with open(path, 'w') as f:
    f.write(content)
PYEOF

  # Clean up schemas/__init__.py (removes reference to deleted user.py)
  truncate -s 0 src/app/schemas/__init__.py

  # Delete auth-related test files and integration marker
  rm -f tests/test_jwt.py tests/test_password.py tests/test_user_api.py
  sed -i '/markers = \[/,/^\]/d' pyproject.toml

  # Delete auth files
  rm -rf src/app/core/security src/app/api/deps src/app/services src/app/schemas/user.py
  rm -f src/app/api/endpoints/user.py
  # Only delete crud/user.py and models/user.py if postgres also disabled
  if [ "$FEAT_POSTGRES" = "n" ]; then
    rm -f src/app/crud/user.py src/app/models/user.py
  fi

  ok "Auth + user module removed."
fi

# Clean up empty __init__.py files after file deletions
find src/app -type f -name '__init__.py' -size 0 -not -path '*__pycache__*' | while read -r f; do
  :  # Keep empty __init__.py files — they're needed for Python packages
done

# ── 7. Auto-format: fix formatting issues from bulk replacements ──────
echo ""
info "Auto-formatting code …"
uv run ruff check --fix --quiet 2>/dev/null && ok "Ruff lint fixed" || warn "Ruff lint skipped"
uv run ruff format --quiet 2>/dev/null && ok "Ruff format applied" || warn "Ruff format skipped"

# ── 8. Handle src/.env — stop tracking, keep local copy ────────────────
if git ls-files --error-unmatch src/.env > /dev/null 2>&1; then
  echo ""
  info "Removing src/.env from git tracking (keeping local copy) …"
  git rm --cached src/.env
  ok "src/.env is now untracked. Each developer runs: cp src/.example.env src/.env"
fi

# ── 9. Output ───────────────────────────────────────────────────────────
echo ""
info "Next steps:"
info "  1. Review the changes:  git diff"
info "  2. Commit:              git add -A && git commit -m \"chore: init \${PROJECT_NAME} project\""
info "  3. Copy .env:           cp src/.example.env src/.env"
info "  4. Edit secrets in      src/.example.env (DB_URL, JWT_SECRET, …)"
info "  5. Start developing:    make dev"
echo ""
