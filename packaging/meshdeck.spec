# RPM spec for MeshDeck (Fedora and other RPM distributions).
#
# Build with packaging/rpm.sh, which:
#   * builds the frontend and the PyInstaller one-file binary,
#   * stages a source tarball rooted at meshdeck-<version>/,
#   * runs `rpmbuild -bb` on this spec and copies the RPM to dist/.
#
# The version comes from meshdeck/version.py via --define on the rpmbuild
# command line (single source of truth); the fallback below only keeps the spec
# syntactically usable with plain `rpmspec`.
%{!?meshdeck_version:%global meshdeck_version 0.1.1}

Name:           meshdeck
Version:        %{meshdeck_version}
Release:        1
Summary:        All-in-one Reticulum application for chat, files, pages and hosting
License:        MIT
URL:            https://github.com/martintondel02/meshdeck
Source0:        meshdeck-%{version}.tar.gz
# The package ships a prebuilt one-file binary; there is no source build here.
# Keep rpm's automatic ELF dependency generation intact (it is correct for the
# bundled PyInstaller binary), but do not try to build a debuginfo subpackage.
%global debug_package %{nil}

%description
MeshDeck is a native Reticulum application for messaging (LXMF), file
sharing, NomadNet-compatible page hosting, and propagation-node hosting.
It runs a local daemon and serves its web UI on 127.0.0.1 only.

This package is unsigned and is built for the glibc/architecture of the host
that produced it; it is not a portable AppImage or Flatpak.

%prep
%setup -q

%build
# The binary is produced by packaging/release.sh / `make package` before this
# spec runs; assert it is present instead of silently packaging nothing.
test -x meshdeck

%install
install -Dm 0755 meshdeck %{buildroot}%{_bindir}/meshdeck
install -Dm 0644 meshdeck.desktop %{buildroot}%{_datadir}/applications/meshdeck.desktop
install -Dm 0644 meshdeck.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/meshdeck.svg
# Explicit path (Fedora's %doc would version it as meshdeck-<version>).
install -Dm 0644 README.md %{buildroot}%{_docdir}/meshdeck/README.md

%files
%{_bindir}/meshdeck
%{_datadir}/applications/meshdeck.desktop
%{_datadir}/icons/hicolor/scalable/apps/meshdeck.svg
%{_docdir}/meshdeck/README.md
%license LICENSE

%changelog
* Mon Oct 19 2026 MeshDeck contributors <noreply@example.invalid> - 0.1.1-1
- Initial RPM packaging for the MeshDeck one-file release binary.
