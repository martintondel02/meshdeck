#!/usr/bin/env bash
# Build a Fedora/RPM-distribution RPM for MeshDeck:
#   frontend build -> PyInstaller one-file binary -> source tarball ->
#   rpmbuild -bb packaging/meshdeck.spec -> dist/meshdeck-<version>-1.<arch>.rpm
#
# Usage: packaging/rpm.sh
# Env:   ARCH=<machine>          override the architecture label (default uname -m)
#        RPMBUILD=/path          use a specific rpmbuild binary
#
# If rpmbuild is not installed, the script tries a user-level route:
# `dnf download rpm-build`, extract it under build/tools/rpmuser, overlay the
# system rpm config dir and run it with RPM_CONFIGDIR. If that cannot work
# without root, the script exits non-zero and produces NO RPM — it never
# fabricates one.
#
# The package is unsigned and targets the build host's glibc/architecture;
# auto-generated ELF Requires are kept (they are correct for the one-file
# PyInstaller binary).
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist"
VERSION_FILE="$ROOT/meshdeck/version.py"
SPEC="$ROOT/packaging/meshdeck.spec"
TOP="$ROOT/build/rpm"

log() { printf '==> %s\n' "$*" >&2; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

for cmd in make pnpm tar sha256sum install mktemp rpm rpm2cpio cpio; do
    command -v "$cmd" >/dev/null 2>&1 || die "required command not found: $cmd"
done

[[ -f "$VERSION_FILE" ]] || die "version file not found: $VERSION_FILE"
[[ -f "$SPEC" ]] || die "spec file not found: $SPEC"
VERSION="$(sed -n 's/^__version__[[:space:]]*=[[:space:]]*"\([^"]*\)".*$/\1/p' "$VERSION_FILE" | head -n 1)"
[[ -n "$VERSION" ]] || die "could not read __version__ from $VERSION_FILE"
[[ "$VERSION" =~ ^[0-9A-Za-z][0-9A-Za-z.+_-]*$ ]] || die "unsafe version string: $VERSION"

ARCH="${ARCH:-$(uname -m)}"
[[ -n "$ARCH" ]] || die "could not determine architecture (uname -m was empty)"

RPMBUILD_BIN=""
RPM_CONFIGDIR_OVERRIDE=""

ensure_rpmbuild() {
    if [[ -n "${RPMBUILD:-}" ]]; then
        [[ -x "$RPMBUILD" ]] || die "RPMBUILD is set but not executable: $RPMBUILD"
        RPMBUILD_BIN="$RPMBUILD"
        log "using rpmbuild from RPMBUILD: $RPMBUILD_BIN"
        return 0
    fi
    if command -v rpmbuild >/dev/null 2>&1; then
        RPMBUILD_BIN="$(command -v rpmbuild)"
        log "using installed rpmbuild: $RPMBUILD_BIN"
        return 0
    fi

    local user="$ROOT/build/tools/rpmuser"
    local cached="$user/usr/bin/rpmbuild"
    if [[ -x "$cached" ]]; then
        RPMBUILD_BIN="$cached"
        RPM_CONFIGDIR_OVERRIDE="$user/usr/lib/rpm"
        log "using cached user-level rpmbuild: $cached"
        return 0
    fi

    command -v dnf >/dev/null 2>&1 || die \
        "rpmbuild is not installed and dnf is unavailable. Install rpm-build (root) and re-run; no RPM was produced."
    local dl="$ROOT/build/tools/rpm-download"
    mkdir -p "$dl"
    rm -f "$dl"/rpm-build-*.rpm
    log "rpmbuild missing; trying user-level route: dnf download rpm-build"
    (cd "$dl" && dnf download rpm-build) || true
    local rpmfile=""
    rpmfile="$(find "$dl" -maxdepth 1 -name 'rpm-build-*.rpm' -print -quit)"
    [[ -n "$rpmfile" ]] || die \
        "could not download rpm-build with dnf (network/repo failure). Install rpm-build (root) and re-run; no RPM was produced."

    log "extracting $rpmfile into $user"
    rm -rf "$user"
    mkdir -p "$user"
    (cd "$user" && rpm2cpio "$rpmfile" | cpio -idm --quiet)
    # rpm-build ships only the build scripts/binaries; the base rpm config
    # (macros, platform, fileattrs) is already installed. Overlay it so the
    # extracted rpmbuild finds macros and the auto-dependency generators.
    local sysconfig
    sysconfig="$(rpm --eval '%{_rpmconfigdir}')"
    [[ -d "$sysconfig" ]] || die "could not locate the system rpm config dir"
    cp -a "$sysconfig/." "$user/usr/lib/rpm/"
    [[ -x "$cached" ]] || die "extracted rpm-build has no rpmbuild binary"
    RPM_CONFIGDIR="$user/usr/lib/rpm" "$cached" --version >/dev/null \
        || die "user-level rpmbuild cannot run (missing library/scripts)"
    RPMBUILD_BIN="$cached"
    RPM_CONFIGDIR_OVERRIDE="$user/usr/lib/rpm"
    log "user-level rpmbuild ready: $cached (RPM_CONFIGDIR=$RPM_CONFIGDIR_OVERRIDE)"
}

ensure_rpmbuild
if [[ -n "$RPM_CONFIGDIR_OVERRIDE" ]]; then
    export RPM_CONFIGDIR="$RPM_CONFIGDIR_OVERRIDE"
fi

log "MeshDeck $VERSION ($ARCH)"
log "building frontend"
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
    (cd "$ROOT/frontend" && pnpm install --frozen-lockfile)
fi
(cd "$ROOT/frontend" && pnpm run build)

log "building PyInstaller binary (make package)"
(cd "$ROOT" && make package)
[[ -x "$DIST/meshdeck" ]] || die "make package did not produce dist/meshdeck"

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/meshdeck-rpm.XXXXXX")"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

# Source tarball with the root rpmbuild/%setup expects.
PKG="$STAGE/meshdeck-$VERSION"
mkdir -p "$PKG"
install -m 0755 "$DIST/meshdeck" "$PKG/meshdeck"
install -m 0644 "$ROOT/packaging/meshdeck.desktop" "$PKG/meshdeck.desktop"
install -m 0644 "$ROOT/packaging/meshdeck.svg" "$PKG/meshdeck.svg"
install -m 0644 "$ROOT/README.md" "$PKG/README.md"
install -m 0644 "$ROOT/LICENSE" "$PKG/LICENSE"

SOURCE_TARBALL="$STAGE/meshdeck-$VERSION.tar.gz"
tar --sort=name --owner=0 --group=0 --numeric-owner \
    -C "$STAGE" -czf "$SOURCE_TARBALL" "meshdeck-$VERSION"

log "staging rpmbuild tree in $TOP"
rm -rf "$TOP"
mkdir -p "$TOP"/{SOURCES,SPECS,BUILD,BUILDROOT,RPMS,SRPMS}
cp "$SOURCE_TARBALL" "$TOP/SOURCES/"

log "running rpmbuild -bb"
"$RPMBUILD_BIN" -bb "$SPEC" \
    --define "_topdir $TOP" \
    --define "_sourcedir $TOP/SOURCES" \
    --define "meshdeck_version $VERSION" \
    --target "$ARCH"

EXPECTED_NAME="meshdeck-$VERSION-1.$ARCH.rpm"
BUILT_RPM="$(find "$TOP/RPMS" -name '*.rpm' -type f -print -quit)"
[[ -n "$BUILT_RPM" ]] || die "rpmbuild reported success but produced no RPM (no fake artifact made)"
[[ "$(basename "$BUILT_RPM")" == "$EXPECTED_NAME" ]] \
    || die "rpmbuild produced $(basename "$BUILT_RPM"), expected $EXPECTED_NAME"

mkdir -p "$DIST"
OUT="$DIST/$EXPECTED_NAME"
rm -f "$OUT"
mv -f "$BUILT_RPM" "$OUT"

log "querying the RPM"
rpm -qip "$OUT" >&2
rpm -qlp "$OUT" >&2

log "extracting and running the packaged binary"
VERIFY="$STAGE/verify-rpm"
mkdir -p "$VERIFY"
(cd "$VERIFY" && rpm2cpio "$OUT" | cpio -idm --quiet)
GOT_VERSION="$("$VERIFY/usr/bin/meshdeck" --version)"
[[ "$GOT_VERSION" == "meshdeck $VERSION" ]] \
    || die "extracted RPM binary reported '$GOT_VERSION', expected 'meshdeck $VERSION'"
log "extracted RPM binary reports: $GOT_VERSION"

log "writing SHA256SUMS entry"
CHECKSUMS="$DIST/SHA256SUMS"
if [[ -f "$CHECKSUMS" ]]; then
    awk -v artifact="$EXPECTED_NAME" '$2 != artifact' "$CHECKSUMS" > "$CHECKSUMS.tmp"
    mv -f "$CHECKSUMS.tmp" "$CHECKSUMS"
fi
(cd "$DIST" && sha256sum "$EXPECTED_NAME" >> SHA256SUMS)

log "artifact: $OUT ($(du -h "$OUT" | cut -f1))"
tail -n 1 "$CHECKSUMS"
