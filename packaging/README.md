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
| RPM | `packaging/rpm.sh` | **verified**: built (Fedora 44, rpmbuild obtained user-level), `rpm -qip`/`-qlp`, extracted with `rpm2cpio`, binary prints the release version |
| Flatpak | `packaging/flatpak/org.meshdeck.MeshDeck.yml` | **verified** (26.08, Builder 1.4.9 user-level): build + install, `--version`, UI + authenticated API served; **caveat:** AutoInterface does not start inside the sandbox |
| Source | `make install && make dev` | documented in the top-level README, not re-verified by this packaging work |

The tarball, AppImage and RPM are built against the host's glibc. They are not
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

## RPM (Fedora, verified on this host)

`packaging/meshdeck.spec` is the **RPM** spec. The PyInstaller spec moved to
`packaging/pyinstaller.spec` (`make package` uses it) when the RPM spec took the
historical name.

```bash
./packaging/rpm.sh
```

The script builds the frontend and `make package`, stages a source tarball
rooted at `meshdeck-<version>/`, runs `rpmbuild -bb`, and writes:

- `dist/meshdeck-<version>-1.<arch>.rpm` (`<arch>` = `uname -m`, no hardcoded
  `x86_64`)
- a `dist/SHA256SUMS` line, replacing any previous line for that artifact

If `rpmbuild` is not installed, `rpm.sh` attempts a **user-level** route:
`dnf download rpm-build`, extract it under `build/tools/rpmuser`, overlay the
system `/usr/lib/rpm` config and run it with `RPM_CONFIGDIR`. This host had no
`rpmbuild` and no root, and that route produced a real RPM. If the route
fails, the script exits non-zero and makes **no** artifact. `RPMBUILD=/path`
overrides the binary.

Install (Fedora/RHEL-family):

```bash
sudo dnf install ./meshdeck-<version>-1.<arch>.rpm
meshdeck --open-browser
```

The package is **unsigned** and **targets the build host's glibc and
architecture**. Auto-generated ELF `Requires` are kept (they are correct for the
bundled one-file binary). The spec deliberately disables the debuginfo
subpackage (`%global debug_package %{nil}`) because there is no source build.

Exact verification recipe:

```bash
VERSION=0.1.1
ARCH=$(uname -m)
rpm -qip dist/meshdeck-$VERSION-1.$ARCH.rpm
rpm -qlp dist/meshdeck-$VERSION-1.$ARCH.rpm
TMP=$(mktemp -d)
(cd "$TMP" && rpm2cpio "$OLDPWD/dist/meshdeck-$VERSION-1.$ARCH.rpm" | cpio -idm)
"$TMP"/usr/bin/meshdeck --version
```

Verified here: `rpm -qip` reports `Version: 0.1.1`, `License: MIT`,
`Signature: (none)`; `rpm -qlp` lists `/usr/bin/meshdeck`,
`/usr/share/applications/meshdeck.desktop`,
`/usr/share/icons/hicolor/scalable/apps/meshdeck.svg`,
`/usr/share/doc/meshdeck/README.md`, `/usr/share/licenses/meshdeck-0.1.1/LICENSE`;
the extracted binary prints `meshdeck 0.1.1`. The artifact is
`meshdeck-0.1.1-1.x86_64.rpm` (~23 MB).

## Flatpak (verified, with a networking caveat)

Verified on Fedora 44 (2026-10-19) with **org.flatpak.Builder 1.4.9** installed
user-level from Flathub (`flatpak install --user -y flathub
org.flatpak.Builder`) and the freedesktop **26.08** runtime/SDK. This host has
no root `flatpak-builder`; the extracted host binary from the `flatpak-builder`
RPM was also used to bypass a Builder-sandbox SDK lookup issue, but the manifest
itself is standard.

- runtime: `org.freedesktop.Platform//26.08`
- sdk: `org.freedesktop.Sdk//26.08`

24.08 also built successfully but is end-of-life on Flathub, so the manifest was
moved to 26.08 (the EOL warning disappeared).

The manifest builds from the source tree with `pip install --prefix=/app`; the
build sandbox needs network for pip, which the manifest now enables with
`build-options.build-args: [--share=network]`. The freedesktop SDK has no
Node/pnpm, so the tree must already contain a built `frontend/dist`
(`make build-frontend`) — the manifest copies it into the installed package.
The `type: dir` source copies the whole tree, so build from a clean copy
without `.venv/` or `node_modules/`.

Recipe used:

```bash
make build-frontend
flatpak remote-add --if-not-exists --user flathub \
    https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y flathub \
    org.flatpak.Builder org.freedesktop.Platform//26.08 org.freedesktop.Sdk//26.08
# clean copy of the tree + built frontend/dist, then:
flatpak run --filesystem=/tmp --command=flatpak-builder org.flatpak.Builder \
    --user --install --force-clean --state-dir=/tmp/flatpak-state \
    /tmp/flatpak-build /tmp/flatpak-src/packaging/flatpak/org.meshdeck.MeshDeck.yml
flatpak run org.meshdeck.MeshDeck --version       # -> meshdeck 0.1.1
```

Verified: build + install succeeded; `--version` printed `meshdeck 0.1.1`; with
`connect_autointerface=false` seeded into the app's data dir, `flatpak run
org.meshdeck.MeshDeck --port 18998` served `GET /` → **200** and authenticated
`GET /api/v1/status` → **200** (`rns_running: true`).

**Caveat (verified, unresolved):** the default AutoInterface does **not** start
inside the Flatpak sandbox on this host — RNS exits **255** before logging a
reason, and the daemon never reaches its API. The app works when AutoInterface
is disabled or a TCP interface is configured, but "Flatpak network discovery"
is **not** verified. Do not claim it.

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
