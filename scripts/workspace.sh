#!/usr/bin/env bash
# Clones (or updates) every DependencyVerifier repository over SSH into one folder, then installs them, as on the
# reference workstation:
#   console      make start (submodules, Docker build, containers, Composer, Yarn, migrations) + a dev super admin
#   agent        cargo build in the rust:1 image (no Rust toolchain needed on the host)
#   agent-image  docker build from the local agent checkout
#   .github      documentation only, nothing to install
#
# Never discards local work: a repository with uncommitted changes, or whose branch has no upstream, is not pulled.
#
# Usage: scripts/workspace.sh [options] [DIR]
#   DIR               target folder (default: the folder that contains this .github checkout)
#   --pull-only       clone / pull only, install nothing
#   --no-super-admin  do not create the dev super admin of the console
#   -h, --help        this help
#
# On a new machine:
#   git clone git@github.com:DependencyVerifier/.github.git ~/Workspace/DepVerifier/.github
#   ~/Workspace/DepVerifier/.github/scripts/workspace.sh

set -euo pipefail

readonly ORG_SSH='git@github.com:DependencyVerifier'
readonly REPOSITORIES='.github console agent agent-image'
readonly CONSOLE_URL='https://console.depverify.localhost'
readonly SUPER_ADMIN_EMAIL='admin@depverify.localhost'

install=1
super_admin=1
target=''
skipped=''

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m  %s\n' "$*" >&2; skipped="${skipped}  - $*"$'\n'; }
fail() { printf '\033[1;31mxx\033[0m  %s\n' "$*" >&2; exit 1; }

usage() {
    sed -n '2,/^$/s/^# \{0,1\}//p' "$0"
}

parse_arguments() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --pull-only) install=0 ;;
            --no-super-admin) super_admin=0 ;;
            -h | --help) usage; exit 0 ;;
            -*) fail "Unknown option: $1 (see --help)" ;;
            *) [ -z "$target" ] || fail 'Only one target folder.'; target="$1" ;;
        esac
        shift
    done

    if [ -z "$target" ]; then
        # scripts/ is inside the .github checkout, which sits in the workspace folder.
        target="$(cd "$(dirname "$0")/../.." && pwd)"
    fi
    mkdir -p "$target"
    target="$(cd "$target" && pwd)"
}

check_prerequisites() {
    local tool
    for tool in git make openssl; do
        command -v "$tool" > /dev/null || fail "$tool is required."
    done

    if [ "$install" -eq 1 ]; then
        command -v docker > /dev/null || fail 'Docker is required (Docker Desktop on macOS).'
        docker info > /dev/null 2>&1 || fail 'Docker is not running: start Docker Desktop, then run the script again.'
    fi

    # The same SSH path as the clones, on a repository of the organization (the repositories are private).
    if ! GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new' git ls-remote "$ORG_SSH/.github.git" HEAD > /dev/null 2>&1; then
        fail 'GitHub refuses the SSH access: add your key (https://github.com/settings/keys) and check you are a member of DependencyVerifier.'
    fi
}

sync_repository() {
    local name="$1" path="$target/$1"

    if [ ! -d "$path/.git" ]; then
        info "Cloning $name"
        git clone --recurse-submodules "$ORG_SSH/$name.git" "$path"
        return
    fi

    if [ -n "$(git -C "$path" status --porcelain --ignore-submodules=dirty)" ]; then
        warn "$name: uncommitted changes, not pulled"
        return
    fi

    if ! git -C "$path" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' > /dev/null 2>&1; then
        warn "$name: branch $(git -C "$path" branch --show-current) has no upstream, not pulled"
        return
    fi

    info "Pulling $name ($(git -C "$path" branch --show-current))"
    git -C "$path" pull --ff-only || { warn "$name: the branch diverged from its upstream, not pulled"; return; }
    git -C "$path" submodule update --init --recursive
}

install_console() {
    info 'Installing console (make start: Docker build, containers, vendors, migrations)'
    make -C "$target/console" start

    [ "$super_admin" -eq 1 ] || return 0
    local credentials="$target/console/var/dev-super-admin.txt"
    if [ -f "$credentials" ]; then
        info "Dev super admin already created (credentials in $credentials)"
        return
    fi

    info "Creating the dev super admin $SUPER_ADMIN_EMAIL"
    local password
    password="$(openssl rand -base64 24)"
    # The password goes through a pipe into a file only its owner can read (the command requires it), never on a
    # command line nor in the output; the file is deleted right after.
    if printf '%s\n' "$password" | docker compose --project-directory "$target/console" exec -T php sh -c '
        umask 077
        file="$(mktemp)"
        cat > "$file"
        bin/console app:user:create-super-admin "$1" --password-file="$file"
        status=$?
        rm -f "$file"
        exit $status
    ' sh "$SUPER_ADMIN_EMAIL"; then
        mkdir -p "$(dirname "$credentials")"
        (umask 077 && printf 'URL: %s\nEmail: %s\nPassword: %s\n' "$CONSOLE_URL" "$SUPER_ADMIN_EMAIL" "$password" > "$credentials")
        info "Credentials written to $credentials (mode 600)"
    else
        warn "console: the dev super admin was not created (it may already exist without $credentials)"
    fi
}

install_agent() {
    info 'Building agent (cargo build in the rust:1 image)'
    docker run --rm -v "$target/agent":/work -w /work -v depverify-cargo-registry:/usr/local/cargo/registry rust:1 cargo build
}

install_agent_image() {
    info 'Building agent-image (from the local agent checkout)'
    docker build --build-context agent-src="$target/agent" -t depverify-agent "$target/agent-image"
}

main() {
    parse_arguments "$@"
    check_prerequisites
    info "Workspace: $target"

    local name
    for name in $REPOSITORIES; do
        sync_repository "$name"
    done

    if [ "$install" -eq 1 ]; then
        install_console
        install_agent
        install_agent_image
    fi

    echo
    info 'Done.'
    [ "$install" -eq 0 ] || printf '    Console: %s (trust the Caddy local CA, or accept the certificate)\n    Mails:   http://localhost:8025\n' "$CONSOLE_URL"
    if [ -n "$skipped" ]; then
        printf '\nNot updated, to check by hand:\n%s' "$skipped"
    fi
}

main "$@"
