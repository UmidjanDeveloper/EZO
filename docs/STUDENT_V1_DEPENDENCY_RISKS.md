# Student V1 dependency risk register

Fresh local Trivy 0.76.0 scan on 2026-10-21: **44 HIGH, zero CRITICAL,
zero fixable HIGH/CRITICAL**. No ignore rules, severity changes or report manipulation.
Raw JSON is retained in the local review evidence. Dependency contents have not been
changed by Student features; rescan the final image and hosted artifacts independently.

Actual image versions: certifi 2026.10.19, lxml 6.1.3, bundled runtime and compiled
libxml2 2.14.6, OpenSSL 3.5.7. Both bundled and system CA stores exclude compromised
emSign ECC G3; unaffected roots and certificate/hostname verification remain enabled.

## Reachability assessment (not proof of non-reachability)

- util-linux family: installed system binaries/libraries; API request handlers do not
  offer arbitrary commands or login/mount administration. Executor intentionally uses
  setpriv/timeout, so local process/privilege preconditions require review. Parser is
  non-root/capability-free; trusted supervisor retains only its reviewed drop/kill caps.
- libacl: no direct application ACL API exposed; filesystem/library operations may
  still load it. Do not claim unreachable merely because Python does not import it.
- ncurses/tinfo: no interactive terminal in parser/HTTP workers; utilities remain in
  image. Reachability through a compromised process is not ruled out.
- systemd/udev libraries: libraries installed, no systemd/udevd service launched in
  these containers; do not infer absence of library-level exposure from daemon absence.
- perl-base: no document-controlled Perl execution path in Student. Installed package
  still contributes residual image risk; a compromised process changes assumptions.

All entries below have **no fixed version in the current scanner database**. The
inherited OS upgrade step already uses the configured signed Debian repositories.
No arbitrary cross-release package replacement or source build was introduced to
claim an unverified patch. These findings remain open; monitor upstream advisories,
rescan with fresh data, review runtime exposure and update pinned base images safely.

| Package | Installed version | Advisory | Fixed version |
| --- | --- | --- | --- |
| bsdutils | 1:2.41.5-0+deb13u1 | CVE-2026-76642 | Unavailable in scan DB |
| bsdutils | 1:2.41.5-0+deb13u1 | CVE-2026-78408 | Unavailable in scan DB |
| bsdutils | 1:2.41.5-0+deb13u1 | CVE-2026-78409 | Unavailable in scan DB |
| bsdutils | 1:2.41.5-0+deb13u1 | CVE-2026-78410 | Unavailable in scan DB |
| libacl1 | 2.3.2-2+b1 | CVE-2026-54369 | Unavailable in scan DB |
| libblkid1 | 2.41.5-0+deb13u1 | CVE-2026-76642 | Unavailable in scan DB |
| libblkid1 | 2.41.5-0+deb13u1 | CVE-2026-78408 | Unavailable in scan DB |
| libblkid1 | 2.41.5-0+deb13u1 | CVE-2026-78409 | Unavailable in scan DB |
| libblkid1 | 2.41.5-0+deb13u1 | CVE-2026-78410 | Unavailable in scan DB |
| liblastlog2-2 | 2.41.5-0+deb13u1 | CVE-2026-76642 | Unavailable in scan DB |
| liblastlog2-2 | 2.41.5-0+deb13u1 | CVE-2026-78408 | Unavailable in scan DB |
| liblastlog2-2 | 2.41.5-0+deb13u1 | CVE-2026-78409 | Unavailable in scan DB |
| liblastlog2-2 | 2.41.5-0+deb13u1 | CVE-2026-78410 | Unavailable in scan DB |
| libmount1 | 2.41.5-0+deb13u1 | CVE-2026-76642 | Unavailable in scan DB |
| libmount1 | 2.41.5-0+deb13u1 | CVE-2026-78408 | Unavailable in scan DB |
| libmount1 | 2.41.5-0+deb13u1 | CVE-2026-78409 | Unavailable in scan DB |
| libmount1 | 2.41.5-0+deb13u1 | CVE-2026-78410 | Unavailable in scan DB |
| libncursesw6 | 6.5+20250216-2 | CVE-2025-69720 | Unavailable in scan DB |
| libsmartcols1 | 2.41.5-0+deb13u1 | CVE-2026-76642 | Unavailable in scan DB |
| libsmartcols1 | 2.41.5-0+deb13u1 | CVE-2026-78408 | Unavailable in scan DB |
| libsmartcols1 | 2.41.5-0+deb13u1 | CVE-2026-78409 | Unavailable in scan DB |
| libsmartcols1 | 2.41.5-0+deb13u1 | CVE-2026-78410 | Unavailable in scan DB |
| libsystemd0 | 257.13-1~deb13u1 | CVE-2026-16742 | Unavailable in scan DB |
| libtinfo6 | 6.5+20250216-2 | CVE-2025-69720 | Unavailable in scan DB |
| libudev1 | 257.13-1~deb13u1 | CVE-2026-16742 | Unavailable in scan DB |
| libuuid1 | 2.41.5-0+deb13u1 | CVE-2026-76642 | Unavailable in scan DB |
| libuuid1 | 2.41.5-0+deb13u1 | CVE-2026-78408 | Unavailable in scan DB |
| libuuid1 | 2.41.5-0+deb13u1 | CVE-2026-78409 | Unavailable in scan DB |
| libuuid1 | 2.41.5-0+deb13u1 | CVE-2026-78410 | Unavailable in scan DB |
| login | 1:4.16.0-2+really2.41.5-0+deb13u1 | CVE-2026-76642 | Unavailable in scan DB |
| login | 1:4.16.0-2+really2.41.5-0+deb13u1 | CVE-2026-78408 | Unavailable in scan DB |
| login | 1:4.16.0-2+really2.41.5-0+deb13u1 | CVE-2026-78409 | Unavailable in scan DB |
| login | 1:4.16.0-2+really2.41.5-0+deb13u1 | CVE-2026-78410 | Unavailable in scan DB |
| mount | 2.41.5-0+deb13u1 | CVE-2026-76642 | Unavailable in scan DB |
| mount | 2.41.5-0+deb13u1 | CVE-2026-78408 | Unavailable in scan DB |
| mount | 2.41.5-0+deb13u1 | CVE-2026-78409 | Unavailable in scan DB |
| mount | 2.41.5-0+deb13u1 | CVE-2026-78410 | Unavailable in scan DB |
| ncurses-base | 6.5+20250216-2 | CVE-2025-69720 | Unavailable in scan DB |
| ncurses-bin | 6.5+20250216-2 | CVE-2025-69720 | Unavailable in scan DB |
| perl-base | 5.40.1-6+deb13u1 | CVE-2026-9538 | Unavailable in scan DB |
| util-linux | 2.41.5-0+deb13u1 | CVE-2026-76642 | Unavailable in scan DB |
| util-linux | 2.41.5-0+deb13u1 | CVE-2026-78408 | Unavailable in scan DB |
| util-linux | 2.41.5-0+deb13u1 | CVE-2026-78409 | Unavailable in scan DB |
| util-linux | 2.41.5-0+deb13u1 | CVE-2026-78410 | Unavailable in scan DB |
