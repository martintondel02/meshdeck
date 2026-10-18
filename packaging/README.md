# MeshDeck packaging and release artifacts

This directory contains the release packaging assets. The version is read from
**`meshdeck/version.py`** (the same value as `meshdeck --version`);
`packaging/release.sh` does not duplicate it.

## Status summary

Verified on **Fedora Linux 44 x86_64** (glibc 2.43) on 2026-10-18, with
PyInstaller 6.22.3 / Python 3.14.8:

| Method | Command | Status |
|---|---|---|
| Tarball | `packaging/release.sh` | **verified**: built, checksummed, extracted, binary ran, UI + API served |
| AppImage | `packaging/appimage.sh` | **verified**: built with appimagetool continuous build 313 (auto-downloaded), `--version`, UI + API served |
| Flatpak | `packaging/flatpak/org.meshdeck.MeshDeck.yml` | **UNVERIFIED**: `flatpak-builder` is not installed on this host; manifest never built |
| Source | `make install && make dev` | documented in the top-level README, not re-verified by this packaging work |

The tarball and AppImage are built against the host's glibc. They are not
portable to older distributions; Flatpak is the intended portable format once
its manifest is verified.

## Tarball (verified)

Build (from the repo root; requires `.venv`, `pnpm`, `make`, network if
`pyinstaller` is not already installed):

```bash
./packaging/release.sh
```

The script builds the frontend, runs `make package`, and writes:

- `dist/meshdeck-<version>-x86_64.tar.gz`
- `dist/SHA256SUMS` (one line per artifact; an AppImage entry is kept if present)

The tarball root is `meshdeck-<version>-x86_64/` and contains exactly:
`meshdeck` (executable), `meshdeck.desktop`, `meshdeck.svg`, `README.md`,
`LICENSE`. The script extracts the finished tarball into a temporary directory
and runs `./meshdeck --version`, failing if the reported version differs from
`meshdeck/version.py`. Re-running overwrites the previous tarball and replaces
only its own `SHA256SUMS` line.

Install for the current user (`Exec=meshdeck` requires `~/.local/bin` on
`PATH`):

```bash
VERSION=0.1.0.dev0
tar -xzf dist/meshdeck-$VERSION-x86_64.tar.gz
install -m 0755 meshdeck-$VERSION-x86_64/meshdeck ~/.local/bin/meshdeck
install -Dm 0644 meshdeck-$VERSION-x86_64/meshdeck.desktop \
    ~/.local/share/applications/meshdeck.desktop
install -Dm 0644 meshdeck-$VERSION-x86_64/meshdeck.svg \
    ~/.local/share/icons/hicolor/scalable/apps/meshdeck.svg
update-desktop-database ~/.local/share/applications 2>/dev/null || true
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor 2>/dev/null || true
meshdeck --open-browser
```

Exact verification recipe:

```bash
cd dist
sha256sum -c SHA256SUMS
tar -tzf meshdeck-$VERSION-x86_64.tar.gz
TMP=$(mktemp -d)
tar -xzf meshdeck-$VERSION-x86_64.tar.gz -C "$TMP"
"$TMP"/meshdeck-$VERSION-x86_64/meshdeck --version
DATA=$(mktemp -d)
"$TMP"/meshdeck-$VERSION-x86_64/meshdeck --data-dir "$DATA" --port 18992 &
sleep 8
curl -fsS -o /dev/null http://127.0.0.1:18992/ && echo "UI OK"
curl -fsS -o /dev/null -H "Authorization: Bearer $(cat "$DATA/token")" \
    http://127.0.0.1:18992/api/v1/status && echo "API OK"
```

`--version`, an unauthenticated `GET /` (`200`) and an authenticated
`GET /api/v1/status` (`200`) were confirmed from a fresh extraction outside the
repo.

## AppImage (verified on this host)

```bash
./packaging/release.sh        # AppImage embeds dist/meshdeck
./packaging/appimage.sh
```

The script assembles `build/appimage/MeshDeck.AppDir` (`usr/bin/meshdeck`,
desktop file, icon, `.DirIcon`, and an `AppRun` that execs the binary), then
runs `appimagetool`. If `appimagetool` is not on `PATH`, it downloads the
official continuous build to `build/tools/appimagetool-x86_64.AppImage`
(verified to be an ELF binary; the cached copy is reused on re-runs, delete it
to re-download). If the tool cannot be obtained or run, the script exits
non-zero and produces **no** AppImage. `APPIMAGETOOL=/path` overrides the
download.

Output: `dist/meshdeck-<version>-x86_64.AppImage`, with its checksum appended to
`dist/SHA256SUMS`.

Exact verification recipe:

```bash
cd dist
sha256sum -c SHA256SUMS
./meshdeck-$VERSION-x86_64.AppImage --version
./meshdeck-$VERSION-x86_64.AppImage --open-browser
# optional: inspect the bundle
./meshdeck-$VERSION-x86_64.AppImage --appimage-extract
ls squashfs-root/AppRun squashfs-root/usr/bin/meshdeck
```

On this host the AppImage was launched directly (FUSE available), reported
`meshdeck 0.1.0.dev0`, and served `GET /` and `GET /api/v1/status` with `200`.
The build warns that AppStream metadata is missing; that is cosmetic. Without
FUSE, run it with `APPIMAGE_EXTRACT_AND_RUN=1`.

## Flatpak (UNVERIFIED)

`flatpak-builder` is **not installed** on this host, so the manifest has never
been built. The runtime/sdk pair is the intended target but was not checked
against Flathub:

- runtime: `org.freedesktop.Platform//24.08`
- sdk: `org.freedesktop.Sdk//24.08`

If that version is retired on the target remote, update both values in the
manifest (for example to `25.08`) before building. The manifest builds from the
source tree with `pip install --prefix=/app`; flatpak-builder needs network
access during the build for pip to fetch hatchling and the runtime dependencies.
The freedesktop SDK has no Node/pnpm, so the tree must already contain a built
`frontend/dist` (`make build-frontend`) — the manifest copies it into the
installed package for the UI to be served. The `type: dir` source copies the
entire working tree (including `.venv/` and `node_modules/` if present), so
verify from a clean checkout or a copy without those directories.

Verification recipe (on a host with Flatpak + flatpak-builder):

```bash
make build-frontend
flatpak remote-add --if-not-exists flathub \
    https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub \
    org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08
flatpak-builder --user --install --force-clean build/flatpak \
    packaging/flatpak/org.meshdeck.MeshDeck.yml
flatpak run org.meshdeck.MeshDeck --version
flatpak run org.meshdeck.MeshDeck --open-browser
```

Do not list Flatpak as a supported install method until this recipe passes and
the manifest's runtime/sdk pair has been confirmed.

## Icon and desktop entry

Both assets are dependency-free (no fonts, no external links, no third-party
artwork) and MIT-licensed with the rest of the repo.

```bash
xmllint --noout packaging/meshdeck.svg
desktop-file-validate packaging/meshdeck.desktop
```

The SVG is a standalone 256×256 icon (rounded dark tile, a 3×3 grid of linked
teal nodes with an amber centre node). The desktop entry uses `Exec=meshdeck`,
`Terminal=false`, `Categories=Network;Chat;`, `Icon=meshdeck`.
