#!/usr/bin/env bash
# Build a MeshDeck AppImage from the already-built dist/meshdeck binary.
#
#   1. assemble an AppDir (usr/bin/meshdeck, desktop file, icon, AppRun)
#   2. use appimagetool if it is installed (or APPIMAGETOOL is set)
#   3. otherwise download the official continuous appimagetool AppImage
#   4. if appimagetool cannot be obtained or run, exit non-zero — no fake
#      AppImage is ever produced.
#
# Usage: packaging/release.sh && packaging/appimage.sh
# Env:   APPIMAGETOOL=/path/to/appimagetool   use a local tool, skip download
#        ARCH=<machine>                       architecture label (default uname -m)
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"
VERSION_FILE="$ROOT/meshdeck/version.py"

log() { printf '==> %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[[ -x "$DIST/meshdeck" ]] \
    || die "dist/meshdeck is missing; run packaging/release.sh (or 'make package') first"
[[ -f "$VERSION_FILE" ]] || die "version file not found: $VERSION_FILE"
VERSION="$(sed -n 's/^__version__[[:space:]]*=[[:space:]]*"\([^"]*\)".*$/\1/p' "$VERSION_FILE" | head -n 1)"
[[ -n "$VERSION" ]] || die "could not read __version__ from $VERSION_FILE"

ARCH="${ARCH:-$(uname -m)}"
case "$ARCH" in
    x86_64) TOOL_ARCH="x86_64" ;;
    aarch64) TOOL_ARCH="aarch64" ;;
    *) die "unsupported architecture '$ARCH' for AppImage" ;;
esac

APPDIR="$ROOT/build/appimage/MeshDeck.AppDir"
APPIMAGE="$DIST/meshdeck-$VERSION-$ARCH.AppImage"

log "assembling AppDir: $APPDIR"
rm -rf "$APPDIR"
mkdir -p \
    "$APPDIR/usr/bin" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/scalable/apps"

install -m 0755 "$DIST/meshdeck" "$APPDIR/usr/bin/meshdeck"
install -m 0644 "$ROOT/packaging/meshdeck.desktop" "$APPDIR/meshdeck.desktop"
install -m 0644 "$ROOT/packaging/meshdeck.desktop" "$APPDIR/usr/share/applications/meshdeck.desktop"
install -m 0644 "$ROOT/packaging/meshdeck.svg" "$APPDIR/meshdeck.svg"
install -m 0644 "$ROOT/packaging/meshdeck.svg" "$APPDIR/.DirIcon"
install -m 0644 "$ROOT/packaging/meshdeck.svg" \
    "$APPDIR/usr/share/icons/hicolor/scalable/apps/meshdeck.svg"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
# AppRun for the MeshDeck AppImage.
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$HERE/usr/bin/meshdeck" "$@"
APPRUN
chmod 0755 "$APPDIR/AppRun"

download_appimagetool() {
    command -v curl >/dev/null 2>&1 || die "appimagetool not found and curl is unavailable; install appimagetool or set APPIMAGETOOL=/path"
    local dir="$ROOT/build/tools"
    local target="$dir/appimagetool-$TOOL_ARCH.AppImage"
    local tmp="$target.part"
    local urls=(
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$TOOL_ARCH.AppImage"
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-$TOOL_ARCH.AppImage"
    )
    mkdir -p "$dir"
    rm -f "$tmp"
    local url
    for url in "${urls[@]}"; do
        log "downloading appimagetool: $url"
        if curl -fL --retry 2 --connect-timeout 15 --max-time 300 \
            -o "$tmp" "$url"; then
            if [[ -s "$tmp" ]] && [[ "$(head -c 4 "$tmp" | od -An -tx1 | tr -d ' \n')" == "7f454c46" ]]; then
                chmod 0755 "$tmp"
                mv -f "$tmp" "$target"
                printf '%s\n' "$target"
                return 0
            fi
            log "download is not an executable AppImage (bad magic); trying next URL"
            rm -f "$tmp"
        else
            rm -f "$tmp"
            log "download failed: $url"
        fi
    done
    return 1
}

TOOL=""
if [[ -n "${APPIMAGETOOL:-}" ]]; then
    [[ -x "$APPIMAGETOOL" ]] || die "APPIMAGETOOL is set but not executable: $APPIMAGETOOL"
    TOOL="$APPIMAGETOOL"
elif command -v appimagetool >/dev/null 2>&1; then
    TOOL="$(command -v appimagetool)"
elif [[ -x "$ROOT/build/tools/appimagetool-$TOOL_ARCH.AppImage" ]]; then
    TOOL="$ROOT/build/tools/appimagetool-$TOOL_ARCH.AppImage"
else
    TOOL="$(download_appimagetool || true)"
fi
if [[ -z "$TOOL" ]]; then
    die "could not obtain appimagetool (not installed and download failed). AppImage NOT built. Install appimagetool or set APPIMAGETOOL=/path/to/appimagetool."
fi
[[ -x "$TOOL" ]] || die "appimagetool is not executable: $TOOL"

log "using appimagetool: $TOOL"
rm -f "$APPIMAGE"
if ! ARCH="$TOOL_ARCH" "$TOOL" "$APPDIR" "$APPIMAGE"; then
    rm -f "$APPIMAGE"
    log "direct appimagetool run failed (FUSE unavailable?); retrying with extraction"
    if ! ARCH="$TOOL_ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APPDIR" "$APPIMAGE"; then
        rm -f "$APPIMAGE"
        die "appimagetool failed to produce an AppImage. AppImage NOT built."
    fi
fi
[[ -s "$APPIMAGE" ]] || die "appimagetool exited successfully but produced no AppImage"

log "writing SHA256SUMS entry"
CHECKSUMS="$DIST/SHA256SUMS"
if [[ -f "$CHECKSUMS" ]]; then
    awk -v artifact="$(basename "$APPIMAGE")" '$2 != artifact' "$CHECKSUMS" > "$CHECKSUMS.tmp"
    mv -f "$CHECKSUMS.tmp" "$CHECKSUMS"
fi
(cd "$DIST" && sha256sum "$(basename "$APPIMAGE")" >> SHA256SUMS)

log "artifact: $APPIMAGE ($(du -h "$APPIMAGE" | cut -f1))"
tail -n 1 "$CHECKSUMS"
