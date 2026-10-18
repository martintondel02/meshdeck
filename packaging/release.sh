#!/usr/bin/env bash
# Build the MeshDeck release tarball:
#   frontend build -> PyInstaller one-file binary -> dist/meshdeck-<version>-<arch>.tar.gz
#
# The tarball contains: meshdeck (binary), meshdeck.desktop, meshdeck.svg,
# README.md, LICENSE. A SHA256SUMS file is written next to it in dist/.
#
# Usage: packaging/release.sh
# Env:   ARCH=<machine>   override the architecture label (default: uname -m)
#
# Re-runnable: previous artifacts and staging directories are replaced.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"
VERSION_FILE="$ROOT/meshdeck/version.py"

log() { printf '==> %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

for cmd in make pnpm tar sha256sum install mktemp; do
    command -v "$cmd" >/dev/null 2>&1 || die "required command not found: $cmd"
done

[[ -f "$VERSION_FILE" ]] || die "version file not found: $VERSION_FILE"
VERSION="$(sed -n 's/^__version__[[:space:]]*=[[:space:]]*"\([^"]*\)".*$/\1/p' "$VERSION_FILE" | head -n 1)"
[[ -n "$VERSION" ]] || die "could not read __version__ from $VERSION_FILE"
[[ "$VERSION" =~ ^[0-9A-Za-z][0-9A-Za-z.+_-]*$ ]] || die "unsafe version string: $VERSION"

ARCH="${ARCH:-$(uname -m)}"
case "$ARCH" in
    x86_64|aarch64|armv7l|riscv64) ;;
    *) die "unsupported architecture '$ARCH' (set ARCH=... to override)" ;;
esac

NAME="meshdeck-$VERSION-$ARCH"
TARBALL="$DIST/$NAME.tar.gz"

log "MeshDeck $VERSION ($ARCH)"
log "building frontend"
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
    (cd "$ROOT/frontend" && pnpm install --frozen-lockfile)
fi
(cd "$ROOT/frontend" && pnpm run build)

log "building PyInstaller binary (make package)"
(cd "$ROOT" && make package)
[[ -x "$DIST/meshdeck" ]] || die "make package did not produce dist/meshdeck"

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/meshdeck-release.XXXXXX")"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

PKG="$STAGE/$NAME"
mkdir -p "$PKG"
install -m 0755 "$DIST/meshdeck" "$PKG/meshdeck"
install -m 0644 "$ROOT/packaging/meshdeck.desktop" "$PKG/meshdeck.desktop"
install -m 0644 "$ROOT/packaging/meshdeck.svg" "$PKG/meshdeck.svg"
install -m 0644 "$ROOT/README.md" "$PKG/README.md"
install -m 0644 "$ROOT/LICENSE" "$PKG/LICENSE"

log "writing $TARBALL"
mkdir -p "$DIST"
rm -f "$TARBALL"
tar --sort=name --owner=0 --group=0 --numeric-owner \
    -C "$STAGE" -czf "$TARBALL" "$NAME"

log "verifying extracted binary"
VERIFY="$STAGE/verify"
mkdir -p "$VERIFY"
tar -xzf "$TARBALL" -C "$VERIFY"
GOT_VERSION="$("$VERIFY/$NAME/meshdeck" --version)"
[[ "$GOT_VERSION" == "meshdeck $VERSION" ]] \
    || die "extracted binary reported '$GOT_VERSION', expected 'meshdeck $VERSION'"
log "extracted binary reports: $GOT_VERSION"

log "writing SHA256SUMS"
CHECKSUMS="$DIST/SHA256SUMS"
if [[ -f "$CHECKSUMS" ]]; then
    # Keep entries from other artifacts (e.g. an AppImage) on re-runs.
    awk -v artifact="$NAME.tar.gz" '$2 != artifact' "$CHECKSUMS" > "$CHECKSUMS.tmp"
    mv -f "$CHECKSUMS.tmp" "$CHECKSUMS"
fi
(cd "$DIST" && sha256sum "$NAME.tar.gz" >> SHA256SUMS)

SIZE="$(du -h "$TARBALL" | cut -f1)"
log "artifact: $TARBALL ($SIZE)"
cat "$DIST/SHA256SUMS"
