#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────
# Instagram MCP Server — Install Script
# Cross-platform (Linux / macOS) — idempotent, safe to rerun
# Usage: curl -fsSL <url> | bash
# ─────────────────────────────────────────────────────────

# ── Colors ────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()    { echo -e "\n${CYAN}▸ $*${NC}"; }

# ── Detect OS ────────────────────────────────────────────
detect_os() {
    case "$(uname -s)" in
        Linux*)  OS="linux" ;;
        Darwin*) OS="macos" ;;
        *)       error "Unsupported OS: $(uname -s)"; exit 1 ;;
    esac
    info "Detected OS: ${OS}"
}

# ── 1. Check Prerequisites ────────────────────────────────
check_prerequisites() {
    step "Checking prerequisites"

    # Git
    if command -v git &>/dev/null; then
        success "git $(git --version | awk '{print $3}')"
    else
        error "git is not installed."
        echo "  Install:  apt install git   (Linux)  |  brew install git   (macOS)"
        exit 1
    fi

    # Python >= 3.12
    if command -v python3 &>/dev/null; then
        PY_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        PY_MAJOR="$(echo "$PY_VERSION" | cut -d. -f1)"
        PY_MINOR="$(echo "$PY_VERSION" | cut -d. -f2)"
        if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 12 ]; then
            success "python ${PY_VERSION}"
        else
            error "Python 3.12+ required (found ${PY_VERSION})."
            echo "  Install:  uv python install 3.12"
            exit 1
        fi
    else
        warn "python3 not found — uv will manage Python."
    fi

    # uv
    if command -v uv &>/dev/null; then
        success "uv $(uv --version)"
        UV_INSTALLED=false
    else
        warn "uv not found — will install."
        UV_INSTALLED=true
    fi
}

# ── 2. Install uv ─────────────────────────────────────────
install_uv() {
    if [ "$UV_INSTALLED" = false ]; then
        return
    fi

    step "Installing uv"
    if curl -LsSf https://astral.sh/uv/install.sh | sh; then
        # Source env so uv is on PATH in this shell
        # uv install.sh writes to $HOME/.cargo/bin or $HOME/.local/bin
        if [ -d "$HOME/.cargo/bin" ] && ! echo "$PATH" | grep -q "$HOME/.cargo/bin"; then
            export PATH="$HOME/.cargo/bin:$PATH"
        fi
        if [ -d "$HOME/.local/bin" ] && ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
            export PATH="$HOME/.local/bin:$PATH"
        fi
        success "uv installed: $(uv --version)"
    else
        error "Failed to install uv."
        echo "  Try manually:  curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
}

# ── 3. Locate or clone the repo ──────────────────────────
REPO_URL="https://github.com/stickerdaniel/instagram-mcp-server"
REPO_NAME="instagram-mcp-server"

locate_or_clone_repo() {
    step "Locating repository"

    # If we are already inside the repo, use it
    if [ -f "pyproject.toml" ] && [ -d "instagram_mcp_server" ]; then
        REPO_DIR="$(pwd)"
        success "Already in repo: ${REPO_DIR}"
        return
    fi

    # Common locations to check
    for candidate in \
        "$HOME/projects/${REPO_NAME}" \
        "$HOME/${REPO_NAME}" \
        "$HOME/dev/${REPO_NAME}" \
        "$HOME/code/${REPO_NAME}"; do
        if [ -f "${candidate}/pyproject.toml" ]; then
            REPO_DIR="${candidate}"
            success "Found repo: ${REPO_DIR}"
            return
        fi
    done

    # Clone into ~/projects/
    REPO_DIR="$HOME/projects/${REPO_NAME}"
    if [ -d "$REPO_DIR" ]; then
        success "Repo already exists: ${REPO_DIR}"
        return
    fi

    info "Cloning repo to ${REPO_DIR} ..."
    mkdir -p "$(dirname "$REPO_DIR")"
    if git clone "${REPO_URL}" "${REPO_DIR}"; then
        success "Cloned to ${REPO_DIR}"
    else
        error "Failed to clone repository."
        echo "  Try manually:  git clone ${REPO_URL} ${REPO_DIR}"
        exit 1
    fi
}

# ── 4. Install Dependencies ──────────────────────────────
install_dependencies() {
    step "Installing dependencies"
    cd "${REPO_DIR}"

    info "Running uv sync ..."
    if uv sync; then
        success "Dependencies installed"
    else
        error "uv sync failed."
        echo "  Try:  cd ${REPO_DIR} && uv sync --reinstall"
        exit 1
    fi

    info "Installing Patchright Chromium ..."
    if uv run patchright install chromium; then
        success "Patchright Chromium installed"
    else
        warn "Patchright Chromium install returned non-zero (may already be cached)."
    fi
}

# ── 5. Check transcription deps (optional) ───────────────
check_transcription_deps() {
    step "Checking optional transcription deps"

    if command -v caption &>/dev/null; then
        success "caption CLI found — reel transcription enabled"
    else
        warn "caption CLI not found."
        echo "  Reel transcription requires: https://github.com/oliverguhr/caption"
        echo "  Alternative: use analyze_reel_with_gemini (no local deps needed)."
    fi
}

# ── 6. Validate Installation ─────────────────────────────
validate_installation() {
    step "Validating installation"
    cd "${REPO_DIR}"

    if uv run python -c "import instagram_mcp_server; print('  Module imported successfully')" 2>/dev/null; then
        success "Module import OK"
    else
        error "Failed to import instagram_mcp_server."
        echo "  Try:  cd ${REPO_DIR} && uv sync --reinstall"
        exit 1
    fi
}

# ── 7. Check Instagram cookies ───────────────────────────
check_instagram_session() {
    step "Checking Instagram session"

    COOKIE_PATH="$HOME/.instagram-mcp/profile/cookies.json"
    if [ -f "$COOKIE_PATH" ]; then
        success "Existing session found at ${COOKIE_PATH}"
        echo "  If session is stale, run:  uv run -m instagram_mcp_server --logout && uv run -m instagram_mcp_server --login"
    else
        warn "No existing Instagram session found."
        echo "  First run:  uv run -m instagram_mcp_server --login"
        echo "  This opens a browser — log in to Instagram to save your session."
    fi
}

# ── 8. Print MCP Configs ─────────────────────────────────
print_mcp_configs() {
    step "MCP Client Configurations"

    echo -e "  ${YELLOW}Copy the config below into your MCP client.${NC}"
    echo ""

    # Claude Desktop
    echo -e "  ${CYAN}Claude Desktop${NC} (~/.config/claude/claude_desktop_config.json):"
    echo '```json'
    echo '{'
    echo '  "mcpServers": {'
    echo '    "instagram": {'
    echo '      "command": "uv",'
    echo '      "args": ["run", "-m", "instagram_mcp_server"],'
    echo '      "cwd": "'"${REPO_DIR}"'"'
    echo '    }'
    echo '  }'
    echo '}'
    echo '```'
    echo ""

    # Cursor
    echo -e "  ${CYAN}Cursor${NC} (.cursor/mcp.json in your workspace):"
    echo '```json'
    echo '{'
    echo '  "mcpServers": {'
    echo '    "instagram": {'
    echo '      "command": "uv",'
    echo '      "args": ["run", "-m", "instagram_mcp_server"],'
    echo '      "cwd": "'"${REPO_DIR}"'"'
    echo '    }'
    echo '  }'
    echo '}'
    echo '```'
    echo ""

    # Windsurf
    echo -e "  ${CYAN}Windsurf${NC} (~/.codeium/windsurf/mcp_config.json):"
    echo '```json'
    echo '{'
    echo '  "mcpServers": {'
    echo '    "instagram": {'
    echo '      "command": "uv",'
    echo '      "args": ["run", "-m", "instagram_mcp_server"],'
    echo '      "cwd": "'"${REPO_DIR}"'"'
    echo '    }'
    echo '  }'
    echo '}'
    echo '```'
    echo ""

    # uvx (no clone needed)
    echo -e "  ${CYAN}Any MCP client (uvx — no clone needed):${NC}"
    echo '```json'
    echo '{'
    echo '  "mcpServers": {'
    echo '    "instagram": {'
    echo '      "command": "uvx",'
    echo '      "args": ["instagram-scraper-mcp"]'
    echo '    }'
    echo '  }'
    echo '}'
    echo '```'
    echo ""
}

# ── 9. Print Next Steps ──────────────────────────────────
print_next_steps() {
    step "Next Steps"

    echo -e "  ${GREEN}1. Add to your MCP client${NC}"
    echo "     Copy one of the configs above into your MCP client's config file."
    echo "     Restart the client after saving."
    echo ""
    echo -e "  ${GREEN}2. First-time login${NC}"
    echo "     Make sure you're logged into Instagram in any supported browser"
    echo "     (Brave, Chrome, Firefox, Edge, etc.), then run:"
    echo "       cd ${REPO_DIR}"
    echo "       uv run -m instagram_mcp_server --login"
    echo ""
    echo -e "  ${GREEN}3. Test the installation${NC}"
    echo "       cd ${REPO_DIR}"
    echo "       uv run -m instagram_mcp_server"
    echo "     The server should start and be ready to accept MCP tool calls."
    echo ""
    echo -e "  ${GREEN}4. Debug (if needed)${NC}"
    echo "       uv run -m instagram_mcp_server --no-headless --log-level DEBUG"
    echo ""
}

# ── Main ──────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}  ${BLUE}Instagram MCP Server — Installer${NC}                           ${GREEN}║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""

    detect_os
    check_prerequisites
    install_uv
    locate_or_clone_repo
    install_dependencies
    check_transcription_deps
    validate_installation
    check_instagram_session
    print_mcp_configs
    print_next_steps

    echo -e "${GREEN}Installation complete!${NC}"
    echo ""
}

main "$@"
