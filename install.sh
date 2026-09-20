#!/usr/bin/env bash
#
# investment-advisor — One-command cold-start bootstrap script.
#
# Usage:
#   ./install.sh [options]
#
# Options:
#   --profile [frugal|balanced|aggressive]  Pre-select operating cost profile
#   --provider [openrouter|ollama|openai]    Pre-select primary LLM provider
#   --api-key KEY                           Set primary LLM provider API key
#   --base-url URL                          Set primary LLM provider base URL
#   --non-interactive                       Run without interactive prompts
#   --skip-build                            Skip rebuilding Docker images
#   --help                                  Show this help message
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PROD_COMPOSE="docker compose --project-name investment_advisor -f docker-compose.prod.yml"

# Colors for terminal output
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
BLUE="\033[0;34m"
NC="\033[0m" # No Color

function log_info {
    echo -e "${BLUE}ℹ${NC} $1"
}

function log_success {
    echo -e "${GREEN}✓${NC} $1"
}

function log_warn {
    echo -e "${YELLOW}⚠️${NC} $1"
}

function log_error {
    echo -e "${RED}✗${NC} $1"
}

function show_banner {
    echo -e "${BOLD}"
    echo "╔═══════════════════════════════════════════════════════════════════════╗"
    echo "║       AI Investment Advisor — Turnkey Installation Bootstrap          ║"
    echo "╚═══════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

function check_prerequisites {
    log_info "Verifying system prerequisites..."

    # 1. Docker
    if ! command -v docker >/dev/null 2>&1; then
        log_error "Docker is not installed. Please install Docker Engine / Docker Desktop first."
        exit 1
    fi

    if ! docker info >/dev/null 2>&1; then
        log_error "Docker daemon is not running. Please start Docker and re-run ./install.sh."
        exit 1
    fi
    log_success "Docker daemon is running."

    # 2. Docker Compose V2
    if docker compose version >/dev/null 2>&1; then
        log_success "Docker Compose V2 found."
    else
        log_error "Docker Compose V2 plugin ('docker compose') is required."
        exit 1
    fi

    # 3. curl
    if ! command -v curl >/dev/null 2>&1; then
        log_error "curl is not installed. Please install curl."
        exit 1
    fi
    log_success "curl found."

    # 4. RAM check
    local total_ram_mb=0
    if [ "$(uname)" = "Darwin" ]; then
        local bytes
        bytes=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
        total_ram_mb=$((bytes / 1024 / 1024))
    elif [ -f /proc/meminfo ]; then
        local kb
        kb=$(grep -m1 MemTotal /proc/meminfo | awk '{print $2}')
        total_ram_mb=$((kb / 1024))
    fi

    if [ "$total_ram_mb" -gt 0 ]; then
        if [ "$total_ram_mb" -lt 3500 ]; then
            log_warn "System RAM is ${total_ram_mb}MB. Recommended minimum is 4096MB (4GB) for the full 7-container stack."
        else
            log_success "System RAM: ${total_ram_mb}MB (≥ 4GB recommended)."
        fi
    fi
}

function ensure_env_file {
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            log_info "Creating .env from .env.example..."
            cp .env.example .env
            log_success "Created .env"
        else
            log_error ".env.example not found. Cannot bootstrap environment."
            exit 1
        fi
    else
        log_success ".env file already exists."
    fi
}

function guard_encryption_keys {
    # Check if a postgres volume already exists
    local db_volume_exists=0
    if docker volume inspect investment_advisor_advisor_db_data >/dev/null 2>&1 \
       || docker volume inspect advisor_db_data >/dev/null 2>&1; then
        db_volume_exists=1
    fi

    if [ "$db_volume_exists" = "1" ]; then
        local missing=""
        for key in APP_SECRET_KEY LLM_CREDENTIAL_KEY; do
            local current=""
            [ -f .env ] && current=$(grep -m1 "^${key}=" .env | cut -d= -f2-)
            case "$current" in ""|*REPLACE_WITH*|*"<replace-with"*) missing="$missing $key" ;; esac
        done

        if [ -n "$missing" ]; then
            echo ""
            log_error "Refusing to bootstrap: an existing database volume was found, but these keys are missing from .env:"
            echo "       ${missing}"
            echo ""
            echo "   These keys decrypt data stored inside that database. Regenerating new keys"
            echo "   would permanently orphan your saved broker and LLM provider credentials."
            echo ""
            echo "   Please restore the original keys into .env (check backups/ or .env.bak-*),"
            echo "   or delete the volume with:  docker volume rm investment_advisor_advisor_db_data"
            exit 1
        fi
    fi
}

function ensure_secret {
    local var_name="$1"
    local generator="${2:-urlsafe}"
    local current=""
    if [ -f .env ]; then
        current=$(grep -m1 "^${var_name}=" .env | cut -d= -f2-)
    fi
    case "$current" in
        ""|*REPLACE_WITH*|*"<replace-with"*|*your-super-secret-key-for-jwt-signing*)
            current=""
            ;;
    esac
    if [ -n "$current" ]; then
        return 0
    fi

    local new_value=""
    if command -v python3 >/dev/null 2>&1; then
        if [ "$generator" = "fernet" ]; then
            new_value=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || true)
        fi
        if [ -z "$new_value" ]; then
            new_value=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))" 2>/dev/null || true)
        fi
    fi

    if [ -z "$new_value" ] && command -v openssl >/dev/null 2>&1; then
        new_value=$(openssl rand -base64 36 | tr -dc 'a-zA-Z0-9' | head -c 48)
    fi

    if [ -z "$new_value" ]; then
        log_warn "Could not auto-generate ${var_name} — please set it manually in .env"
        return 1
    fi

    if grep -q "^${var_name}=" .env 2>/dev/null; then
        sed -i.bak "s|^${var_name}=.*|${var_name}=${new_value}|" .env && rm -f .env.bak
    else
        echo "${var_name}=${new_value}" >> .env
    fi
    log_success "Generated secure ${var_name}"
}

function ensure_literal {
    local var_name="$1" value="$2" current=""
    [ -f .env ] && current=$(grep -m1 "^${var_name}=" .env | cut -d= -f2-)
    [ -n "$current" ] && return 0
    echo "${var_name}=${value}" >> .env
    log_success "Set ${var_name}=${value}"
}

function wait_for_api {
    local max_wait=120
    local waited=0
    echo -n "Waiting for API to be ready..."
    while [ $waited -lt $max_wait ]; do
        if curl -sf "http://localhost:8000/health" >/dev/null 2>&1 || curl -sf "http://localhost:8001/health" >/dev/null 2>&1; then
            echo ""
            log_success "API is ready (${waited}s)"
            return 0
        fi
        sleep 3
        waited=$((waited + 3))
        echo -n "."
    done
    echo ""
    log_warn "API did not respond within ${max_wait}s. Checking logs..."
    return 1
}

# ─────────────────────────────────────────────────────────────────────────────
# Main Bootstrap Workflow
# ─────────────────────────────────────────────────────────────────────────────

show_banner

PROFILE=""
PROVIDER=""
API_KEY=""
BASE_URL=""
NON_INTERACTIVE=0
SKIP_BUILD=0

while [ $# -gt 0 ]; do
    case "$1" in
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --provider)
            PROVIDER="$2"
            shift 2
            ;;
        --api-key)
            API_KEY="$2"
            shift 2
            ;;
        --base-url)
            BASE_URL="$2"
            shift 2
            ;;
        --non-interactive)
            NON_INTERACTIVE=1
            shift
            ;;
        --skip-build)
            SKIP_BUILD=1
            shift
            ;;
        --help|-h)
            echo "Usage: ./install.sh [options]"
            echo ""
            echo "Options:"
            echo "  --profile [frugal|balanced|aggressive]  Select cost profile"
            echo "  --provider [openrouter|ollama|openai]    Select primary LLM provider"
            echo "  --api-key KEY                           Set primary provider API key"
            echo "  --base-url URL                          Set primary provider endpoint URL"
            echo "  --non-interactive                       Run non-interactively"
            echo "  --skip-build                            Skip building container images"
            exit 0
            ;;
        *)
            log_warn "Unknown argument '$1' ignored."
            shift
            ;;
    esac
done

check_prerequisites
ensure_env_file
guard_encryption_keys

log_info "Ensuring deployment secrets..."
ensure_secret "LLM_CREDENTIAL_KEY" "fernet"
ensure_secret "APP_SECRET_KEY" "fernet"
ensure_secret "DB_PASS" "urlsafe"
ensure_secret "REDIS_PASSWORD" "urlsafe"
ensure_literal "DB_USER" "postgres"
ensure_literal "DB_NAME" "advisor_prod"

# Interactive wizard if terminal is interactive and no explicit flags
if [ -t 0 ] && [ "$NON_INTERACTIVE" -eq 0 ] && [ -z "$PROFILE" ] && [ -z "$PROVIDER" ]; then
    echo ""
    echo -e "${BOLD}Setup Step 1: Operating Cost Profile (運算成本方案)${NC}"
    echo "Controls how often autonomous agents scan the markets and model tier budgets."
    echo "  [1] Balanced (Default) — 15-min scans, smart reasoning for councils (~$15-25/wk)"
    echo "  [2] Frugal             — 30-min scans, nano-first models (~$2-5/wk, or $0 with Ollama)"
    echo "  [3] Aggressive         — 5-min scans, deep multi-tier analysis (~$50-100/wk)"
    printf "Choose option [1-3] (Enter for Balanced): "
    read -r profile_choice
    case "$profile_choice" in
        2|frugal)      PROFILE="frugal" ;;
        3|aggressive)  PROFILE="aggressive" ;;
        *)             PROFILE="balanced" ;;
    esac
    log_success "Selected Cost Profile: ${PROFILE}"

    echo ""
    echo -e "${BOLD}Setup Step 2: Primary AI Model Provider (主要 LLM 提供商)${NC}"
    echo "Agents require an LLM to generate market intelligence and council decisions."
    echo "  [1] OpenRouter (Recommended: single key for Claude, GPT, Llama, and open models)"
    echo "  [2] Ollama     (Local LLM running on your computer, $0 API cost)"
    echo "  [3] OpenAI     (Direct GPT-4o / o3-mini access)"
    echo "  [4] Skip       (Configure later in Settings -> AI Engine)"
    printf "Choose option [1-4] (Enter for OpenRouter): "
    read -r provider_choice
    case "$provider_choice" in
        2|ollama)
            PROVIDER="ollama"
            printf "Enter Ollama Base URL [http://host.docker.internal:11434]: "
            read -r url_input
            BASE_URL="${url_input:-http://host.docker.internal:11434}"
            ;;
        3|openai)
            PROVIDER="openai"
            printf "Enter OpenAI API Key (sk-...): "
            read -r key_input
            API_KEY="$key_input"
            ;;
        4|skip)
            PROVIDER="skip"
            ;;
        *)
            PROVIDER="openrouter"
            printf "Enter OpenRouter API Key (sk-or-...): "
            read -r key_input
            API_KEY="$key_input"
            ;;
    esac
    log_success "Selected Provider: ${PROVIDER}"
fi

# Fallbacks
PROFILE="${PROFILE:-balanced}"
PROVIDER="${PROVIDER:-skip}"

# Build and bring up stack
if [ "$SKIP_BUILD" -eq 0 ]; then
    log_info "Building container images..."
    $PROD_COMPOSE build
fi

log_info "Starting single-box services..."
$PROD_COMPOSE up -d --remove-orphans

wait_for_api || true

log_info "Applying database migrations..."
docker exec advisor_prod_api alembic upgrade head
log_success "Database migrations applied."

log_info "Seeding safe defaults..."
docker exec advisor_prod_api python -c "
from src.config.owner import get_owner_id
from src.services.settings_service import SettingsService
owner = get_owner_id()
print(f'  ✓ Owner ID: {owner}')
svc = SettingsService(user_id=owner)
if svc.get_setting('ai_trading_enabled') is None:
    svc.save_settings_bulk({'ai_trading_enabled': False})
    print('  ✓ ai_trading_enabled=false (safety brake enabled)')
"

log_info "Applying initial onboarding configuration..."
docker exec advisor_prod_api python scripts/onboarding_wizard.py \
    --profile "$PROFILE" \
    --provider "$PROVIDER" \
    ${API_KEY:+--api-key "$API_KEY"} \
    ${BASE_URL:+--base-url "$BASE_URL"} \
    --non-interactive

echo ""
log_info "Verifying deployment health..."
if ./start.sh health; then
    echo ""
    echo -e "${GREEN}${BOLD}═══════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}${BOLD}  ✓ INSTALLATION SUCCESSFUL! System is healthy and operational.        ${NC}"
    echo -e "${GREEN}${BOLD}═══════════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  🌐 Dashboard:   ${BOLD}http://127.0.0.1:8088${NC}  (Local Loopback, No Login Needed)"
    echo -e "  ⚙️  Extensions:  ${BOLD}http://127.0.0.1:8088/extensions${NC}"
    echo -e "  🤖 Agents:      ${BOLD}http://127.0.0.1:8088/agents${NC}"
    echo -e "  📊 Workflows:   ${BOLD}http://127.0.0.1:8088/workflows${NC}"
    echo ""
    echo "  Commands:"
    echo "    ./start.sh health      Check running status"
    echo "    ./start.sh backup      Create database and config snapshot"
    echo "    ./start.sh upgrade     Pull updates and apply migrations"
    echo "    ./start.sh logs        Inspect live container logs"
    echo "    ./start.sh down        Stop the stack"
    echo ""

    # Open browser on macOS / Linux desktop if interactive
    if [ -t 0 ] && [ "$NON_INTERACTIVE" -eq 0 ]; then
        if command -v open >/dev/null 2>&1; then
            open "http://127.0.0.1:8088" 2>/dev/null || true
        elif command -v xdg-open >/dev/null 2>&1; then
            xdg-open "http://127.0.0.1:8088" 2>/dev/null || true
        fi
    fi
else
    log_warn "Stack is running, but one or more health checks failed."
    echo "Inspect container status with:  ./start.sh logs"
fi
