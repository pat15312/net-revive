# Final production image advisories

Grype 0.118.0, database built see scan-summary.json. Raw severity is the scanner label, not a demonstrated NetRevive exploit. Package duplication is collapsed below; the machine summary retains match counts. No advisories were suppressed.

## Reachability review

- **Perl/archive utilities, gzip, tar, ncurses/PCRE2:** NetRevive does not invoke these interpreters/tools or accept archive uploads/regular expressions. Perl 32-bit findings do not describe the shipped 64-bit architectures. These remain installed base-image packages, not removed from scanner accounting.
- **glibc:** reviewed high/critical descriptions concern `%mc` scanf, wide-character stdio pushback and deprecated DNS pretty-printing. No application path calls those APIs with attacker input. This is source-path analysis, not exhaustive proof about every native dependency.
- **SQLite FTS5:** the app has no full-text-search virtual tables/MATCH queries and no untrusted database upload/restore endpoint. Only fixed parameterized application SQL runs. Restoring a malicious database is outside supported operation.
- **util-linux/mount/nsenter/ACL/PAM:** require privileged local execution, mount configuration or local filesystem influence. Production runs as UID 10001 with no capabilities, no-new-privileges and read-only code. No application subprocess calls or Docker socket mounts exist.
- **zlib:** the reported high-severity path is nonblocking gzwrite/gzprintf; the app does not use those operations. Controller compression is explicitly rejected.
- **Python:** identified medium/low findings concern stdlib functionality; retain stable Python 3.14 rather than introduce a 3.15 prerelease merely to satisfy a broad CPE match. Reassess on stable patch releases.

The Debian tracker marks several of these as minor/no-DSA or postponed; that does not erase the upstream issue. No fixable High/Critical matches remain in this scan. No remotely reachable High/Critical path was demonstrated in these base packages, but the image is **not vulnerability-free**. Refresh the pinned base and repeat scans; future code/dependency changes may alter reachability.

## Inventory

| Advisory | Raw severity | Packages | Scanner fix state | Source |
| --- | --- | --- | --- | --- |
| CVE-2005-2541 | Negligible | tar | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2005-2541) |
| CVE-2007-5686 | Negligible | login.defs, passwd | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2007-5686) |
| CVE-2010-4756 | Negligible | libc-bin, libc6 | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2010-4756) |
| CVE-2011-3374 | Negligible | apt, libapt-pkg7.0 | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2011-3374) |
| CVE-2011-4116 | Negligible | perl-base | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2011-4116) |
| CVE-2013-4392 | Negligible | libsystemd0, libudev1 | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2013-4392) |
| CVE-2017-18018 | Negligible | coreutils | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2017-18018) |
| CVE-2018-20796 | Negligible | libc-bin, libc6 | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2018-20796) |
| CVE-2019-1010022 | Negligible | libc-bin, libc6 | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2019-1010022) |
| CVE-2019-1010023 | Negligible | libc-bin, libc6 | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2019-1010023) |
| CVE-2019-1010024 | Negligible | libc-bin, libc6 | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2019-1010024) |
| CVE-2019-1010025 | Negligible | libc-bin, libc6 | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2019-1010025) |
| CVE-2019-9192 | Negligible | libc-bin, libc6 | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2019-9192) |
| CVE-2021-45346 | Negligible | libsqlite3-0 | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2021-45346) |
| CVE-2022-0563 | Negligible | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2022-0563) |
| CVE-2023-31437 | Negligible | libsystemd0, libudev1 | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2023-31437) |
| CVE-2023-31438 | Negligible | libsystemd0, libudev1 | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2023-31438) |
| CVE-2023-31439 | Negligible | libsystemd0, libudev1 | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2023-31439) |
| CVE-2024-56433 | Low | login.defs, passwd | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2024-56433) |
| CVE-2025-15367 | Medium | python | fixed: 3.15.0a6 | [advisory](https://nvd.nist.gov/vuln/detail/CVE-2025-15367) |
| CVE-2025-15649 | Medium | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2025-15649) |
| CVE-2025-5278 | Negligible | coreutils | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2025-5278) |
| CVE-2025-6141 | Medium | libncursesw6, libtinfo6, ncurses-base, ncurses-bin | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2025-6141) |
| CVE-2025-69720 | High | libncursesw6, libtinfo6, ncurses-base, ncurses-bin | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2025-69720) |
| CVE-2025-70873 | Negligible | libsqlite3-0 | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2025-70873) |
| CVE-2026-11822 | High | libsqlite3-0 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-11822) |
| CVE-2026-11824 | High | libsqlite3-0 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-11824) |
| CVE-2026-12087 | Critical | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-12087) |
| CVE-2026-13221 | Critical | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-13221) |
| CVE-2026-15059 | Medium | libsystemd0, libudev1 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-15059) |
| CVE-2026-15310 | Low | python | fixed: 3.15.0rc2 | [advisory](https://nvd.nist.gov/vuln/detail/CVE-2026-15310) |
| CVE-2026-15534 | Medium | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-15534) |
| CVE-2026-15806 | Medium | python | fixed: 3.15.0rc2 | [advisory](https://nvd.nist.gov/vuln/detail/CVE-2026-15806) |
| CVE-2026-16742 | Medium | libsystemd0, libudev1 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-16742) |
| CVE-2026-17084 | Medium | python | fixed: 3.15.0rc2 | [advisory](https://nvd.nist.gov/vuln/detail/CVE-2026-17084) |
| CVE-2026-18374 | Medium | libc-bin, libc6 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-18374) |
| CVE-2026-18477 | Medium | tar | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-18477) |
| CVE-2026-18508 | Medium | tar | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-18508) |
| CVE-2026-19487 | Medium | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-19487) |
| CVE-2026-19499 | Unknown | libc-bin, libc6 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-19499) |
| CVE-2026-19542 | Unknown | libc-bin, libc6 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-19542) |
| CVE-2026-19672 | Medium | python |  | [advisory](https://nvd.nist.gov/vuln/detail/CVE-2026-19672) |
| CVE-2026-27171 | Medium | zlib1g | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-27171) |
| CVE-2026-3184 | Medium | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-3184) |
| CVE-2026-39113 | Medium | libsqlite3-0 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-39113) |
| CVE-2026-40228 | Low | libsystemd0, libudev1 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-40228) |
| CVE-2026-41991 | Medium | gzip | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-41991) |
| CVE-2026-41992 | High | gzip | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-41992) |
| CVE-2026-42250 | Medium | libbz2-1.0 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-42250) |
| CVE-2026-42496 | Critical | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-42496) |
| CVE-2026-42497 | High | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-42497) |
| CVE-2026-4360 | Medium | python |  | [advisory](https://nvd.nist.gov/vuln/detail/CVE-2026-4360) |
| CVE-2026-48959 | High | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-48959) |
| CVE-2026-48961 | High | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-48961) |
| CVE-2026-48962 | High | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-48962) |
| CVE-2026-50812 | Medium | libsqlite3-0 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-50812) |
| CVE-2026-50813 | Medium | libsqlite3-0 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-50813) |
| CVE-2026-53910 | Negligible | diffutils | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-53910) |
| CVE-2026-5435 | High | libc-bin, libc6 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-5435) |
| CVE-2026-54369 | High | libacl1 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-54369) |
| CVE-2026-54370 | High | libacl1 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-54370) |
| CVE-2026-54371 | Medium | libattr1 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-54371) |
| CVE-2026-54411 | Medium | libpam-modules, libpam-modules-bin, libpam-runtime, libpam0g | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-54411) |
| CVE-2026-5450 | Critical | libc-bin, libc6 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-5450) |
| CVE-2026-56391 | Negligible | coreutils | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-56391) |
| CVE-2026-56392 | Negligible | coreutils | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-56392) |
| CVE-2026-5704 | Medium | tar | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-5704) |
| CVE-2026-57432 | High | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-57432) |
| CVE-2026-57433 | Critical | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-57433) |
| CVE-2026-5928 | High | libc-bin, libc6 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-5928) |
| CVE-2026-6238 | Medium | libc-bin, libc6 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-6238) |
| CVE-2026-6368 | Low | libc-bin, libc6 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-6368) |
| CVE-2026-6791 | Medium | libc-bin, libc6 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-6791) |
| CVE-2026-7010 | Medium | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-7010) |
| CVE-2026-7017 | High | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-7017) |
| CVE-2026-76642 | High | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-76642) |
| CVE-2026-77117 | Unknown | libc-bin, libc6 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-77117) |
| CVE-2026-78408 | High | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-78408) |
| CVE-2026-78409 | High | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-78409) |
| CVE-2026-78410 | High | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-78410) |
| CVE-2026-80489 | Unknown | libc-bin, libc6 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-80489) |
| CVE-2026-8376 | Critical | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-8376) |
| CVE-2026-85091 | High | zlib1g | not-fixed | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-85091) |
| CVE-2026-86145 | High | libpcre2-8-0 | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-86145) |
| CVE-2026-9538 | High | perl-base | wont-fix | [advisory](https://security-tracker.debian.org/tracker/CVE-2026-9538) |
