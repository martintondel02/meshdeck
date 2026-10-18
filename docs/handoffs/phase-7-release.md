# Phase 7 / v0.2.0 release record

> **Status:** release gate executed 2026-10-19 from base `31d8fbb` (v0.1.1).
> This is the evidence file; the release report repeats only what was run.

## Test evidence (tagged tree)

```
$ .venv/bin/python -m pytest tests/unit -q
160 passed in 0.47s

$ .venv/bin/ruff check meshdeck tests
All checks passed!

$ .venv/bin/python -m pytest tests/api tests/integration -m integration -q
26 passed, 3 warnings in 84.51s (0:01:24)

$ cd frontend && pnpm run check
svelte-check found 0 errors and 0 warnings
$ pnpm run test
Test Files  2 passed (2)
     Tests  37 passed (37)
$ pnpm run build
dist/assets/index-BEF8n2Z8.js   167.54 kB │ gzip: 53.82 kB
✓ built in 620ms

$ MESHDECK_INTEROP_PYTHON=/tmp/interop/bin/python \
  MESHDECK_INTEROP_NOMADNET=/tmp/interop/bin/nomadnet \
  MESHDECK_INTEROP_LXMD=/tmp/interop/bin/lxmd \
  .venv/bin/python -m pytest tests/interop -m interop -q
4 passed in 76.05s (0:01:16)
```

## Artifacts (rebuilt from the 0.2.0 tree)

| Artifact | Bytes | SHA-256 |
|---|---|---|
| `meshdeck-0.2.0-x86_64.tar.gz` | 23,189,489 | `b65ce3e49576ef63a11053ec8978f82c8b4fdbc6f2d314436159eb40de46fb9a` |
| `meshdeck-0.2.0-x86_64.AppImage` | 24,164,856 | `d93d7189494ca8706c834184518913b03c55646c16733a32232b8628d1f65682` |
| `meshdeck-0.2.0-1.x86_64.rpm` | 23,200,124 | `42da3c7f28563bf2339d2c071037ae76560a739ab5820f0872b2e12bc7010eb6` |

```
$ cd dist && sha256sum -c SHA256SUMS
meshdeck-0.2.0-x86_64.tar.gz: OK
meshdeck-0.2.0-x86_64.AppImage: OK
meshdeck-0.2.0-1.x86_64.rpm: OK
```

All three were started with a temp data dir and a loopback HTTP port:

```
tarball:  version "meshdeck 0.2.0", GET / -> 200, GET /api/v1/status -> 200, rns=true
AppImage: version "meshdeck 0.2.0", GET / -> 200, GET /api/v1/status -> 200, rns=true
RPM:      version "meshdeck 0.2.0", GET / -> 200, GET /api/v1/status -> 200, rns=true
```

Tarball root contains exactly `meshdeck-0.2.0-x86_64/{meshdeck,meshdeck.desktop,meshdeck.svg,README.md,LICENSE}`.

RPM query/extract:

```
$ rpm -qip dist/meshdeck-0.2.0-1.x86_64.rpm
Name        : meshdeck
Version     : 0.2.0
Release     : 1
Architecture: x86_64
License     : MIT
Signature   : (none)
URL         : https://github.com/martintondel02/meshdeck

$ rpm -qpR ...            # auto-generated ELF requires kept
libc.so.6()(64bit) ... libdl.so.2 ... libpthread.so.0 ... libz.so.1 ...

$ rpm -qlp ...
/usr/bin/meshdeck
/usr/share/applications/meshdeck.desktop
/usr/share/doc/meshdeck/README.md
/usr/share/icons/hicolor/scalable/apps/meshdeck.svg
/usr/share/licenses/meshdeck-0.2.0
/usr/share/licenses/meshdeck-0.2.0/LICENSE
```

The RPM was extracted with `rpm2cpio | cpio -idm` and its
`usr/bin/meshdeck --version` printed `meshdeck 0.2.0`.

## Release

- Tag: `v0.2.0` (annotated, on the release commit).
- GitHub release: `https://github.com/martintondel02/meshdeck/releases/tag/v0.2.0`
  with tarball, AppImage, RPM and `SHA256SUMS`.
- Release assets were downloaded again and re-verified (checksums, versions);
  see the final report for the exact commands/output.
- CI: backend (3.12/3.13/3.14), frontend, and the integration job were checked
  on the release commit; see the final report for the run URL/status.

## Verified vs unverified

Verified: unit/API/integration/frontend/interop suites; keyboard-only flow;
Orca attached + utterances logged (not heard); Flatpak build/install/version/
UI/API; timed fresh clone; all three artifacts' checksums, `--version`,
UI+API; RPM query/extract.

Unverified / limitations: Flatpak AutoInterface in the sandbox; screen-reader
announcements heard by a human; cold-cache/human fresh-clone timing; Sideband/
Android/iOS, NomadNet TUI, lxmd autopeering, large interop transfers, stamp
costs >13, Windows/macOS; RPM signing and older-glibc portability; automatic
VACUUM; instantaneous propagation-store enforcement.
