# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- **Feed dedup of covered more-specifics (`--aggregate-classes`), on by default.** `collapse_networks` only dedups within a single source, so a `/32` from one list nested inside a `/24` from another survives — on the live feed ~33k such routes (30%) are blocked `/32`s sitting under a foreign-service or CDN `/24`. Dedup drops a more-specific when a covering supernet shares its community *class* (a range that every export filter accepts/rejects as a whole), cutting the feed ~30% (vps02: 111048 → 77337) with identical longest-match forwarding for peers on `export_only_ru`/`export_blocked_lists`. Runs by default with classes `100-199,200-399`; `--aggregate-classes` overrides the ranges, `--no-aggregate` disables it. **Fail-closed safety:** before applying, the run scans `--peers-dir` (default `/etc/bird/peers.d`) and rejects any peer filter whose accept-range only partially overlaps a class (e.g. `export_blocked_only` 200-299 vs class 200-399), an unknown named filter, or an inline filter referencing `bgp_community` — those could still need a route dedup would drop. An explicit `--aggregate-classes` makes a mismatch fatal; the default path degrades gracefully to the full feed so an unrelated peer change can't stall updates.
- **Own-infrastructure exclusion (anti-loop).** The updater now subtracts your own networks from the feed before writing it, so a prefix covering your egress next-hop can never be advertised (which would create a routing loop). The list is the manually maintained `/etc/bird/own-infra.lst` (override via `OWN_INFRA_FILE`); it ships as an empty template (no infrastructure is committed to this public repo) and is mandatory — a missing or empty file is fatal (fail-closed). Subtraction is source-agnostic and hole-punches supernets via `ipaddress.address_exclude`, with a fail-closed self-check that aborts the run if any own-infra prefix survives.
- Added `if net ~ OWN_INFRA then reject;` as the first statement of every named export filter (`export_only_ru`, `export_blocked_lists`, `export_blocked_only`, `export_services_only`, `export_complex_logic`) and the `t_client` template in `conf/bird.conf`, as a second (belt-and-suspenders) layer. Named filters must each be guarded because peers override the template's anonymous filter. (`OWN_INFRA` itself is generated into `own-infra.conf` — see Changed.)
- Added `conf/own-infra.lst` inventory template (installed to `/etc/bird/own-infra.lst`).
- Added RIPEstat sources for Meta/Facebook AS32934 (`380`), Twitter/X AS13414 (`381`), Netflix AS2906/AS40027 (`382`), YouTube AS36040/AS43515 (`386`), and Anthropic AS399358 (`387`).
- Added full Cloudflare AS13335 as a RIPEstat source (community `384`, ~2400 prefixes). The existing `official_services` (comm `300`) only carries Cloudflare's published CDN ranges (`cloudflare.com/ips-v4`, ~15 blocks); AS13335 announces many more, incl. non-published blocks like `8.6.112.0/24` that front `chatgpt.com`. Without it, DNS handing out such an IP leaks past the tunnel.
- Added Threema as a static-prefix source: PI block `203.56.112.0/22` (community `388`). Threema has no own ASN — its PI space is announced via shared upstreams (AS29691/AS15576) — so a new `static` source type was added instead of the per-ASN RIPEstat pattern.
- Added matching BIRD community constants for the new service sources.
- Added filtered AWS CloudFront IPv4 prefixes from AWS `ip-ranges.json` as community `383`.

### Changed
- Raised the BIRD client-template `export limit` from `200000` to `500000`. Adding the full Cloudflare AS13335 source (~2400 prefixes) shrank the headroom over the live feed (~103k); the limit uses `action disable`, so it must stay well above the feed to avoid dropping client sessions as the RU/blocked lists grow.
- **`OWN_INFRA` is now generated, not hand-edited.** The updater writes `define OWN_INFRA = [...]` to `/etc/bird/own-infra.conf` from the same `own-infra.lst` inventory, and `bird.conf` pulls it in via `include`. This removes deployment-local data from the git-tracked `bird.conf` (so it can be reinstalled from git on every update without clobbering real own-infra) and makes `own-infra.lst` the single source of truth for both L1 subtraction and L2 export filters. Run the updater before `birdc configure` so the include exists.

### Fixed
- Replaced permissive IPv4 parsing with strict `ipaddress`-based validation.
- Replaced shell-based BIRD commands with argv-based `subprocess.run` calls.
- Write `prefixes.txt` only after the generated BIRD configuration passes smoke testing, and repair it when the BIRD output is unchanged but the text output is missing or stale.
- Treat Netflix and YouTube as all-or-fallback multi-AS sources so partial RIPEstat failures do not publish partial service communities.
- Removed stale current-facing documentation for unsupported `RIPESTAT_URL` overrides and corrected the documented BIRD export limit.
- Bumped `USER_AGENT` to `BIRD2-BGP-Prefix-Updater/3.4`.

### Removed
- Removed inactive `blocked_sum` / `blocked_smart` source stubs and unused BIRD constants for communities `220` and `230`.
- Replaced the active LastPass sample entries in `conf/custom.lst` with commented examples so new installs start with an empty local custom list.

## [3.2.0] - 2026-05-11
### Changed
- **BREAKING: BGP community renumbering by semantic group (hundreds-based scheme).** Community IDs are now grouped by meaning rather than assignment order:
  - `100..199` — Russian resources (route via local Russian channel)
  - `200..299` — RKN-blocked subnets (route around blocking)
  - `300..399` — Foreign services (also routed around blocking)
- **Why:** `gov_networks` (`govno.lst`) is a Russian government resource and logically belongs with RU Combined, not in the same range as foreign blocked services like Stripe, Cloudflare or Akamai. Filters using a single `101..112` range incorrectly bundled gov networks with foreign services. The new scheme makes filter ranges self-documenting.
- Old → new community ID mapping:
  - `100` → `100` ru_combined (unchanged)
  - `103` → **`110`** gov_networks (moved into RU group)
  - `106` → `200` blocked_ip
  - `102` → `210` rkn_subnets
  - `104` → `300` official_services (Telegram/Cloudflare/Google/local custom.lst)
  - `104` → **`310`** custom_user (now distinct from official_services)
  - `107` → `320` stripe_networks
  - `108` → `330` bytedance_as396986
  - `109` → `340` akamai_as20940
  - `110` → `350` roblox_as22697
  - `111` → `360` pinterest_as53620
  - `112` → `370` fastly_as54113
- BIRD filters in `conf/bird.conf` rewritten to use the new ranges:
  - `export_only_ru` now accepts `100..199` (was: accept 100, reject 101..112)
  - `export_blocked_lists` now accepts `200..399` (was: accept 101..112)
  - Added `export_blocked_only` (`200..299`) and `export_services_only` (`300..399`) for finer control
- README.md and README_EN.md now include cross-language navigation links at the top and reflect the new community scheme.
- `USER_AGENT` bumped to `BIRD2-BGP-Prefix-Updater/3.2`.

### Migration
1. Pull latest: `git pull`.
2. Install new files: `install -m644 conf/bird.conf /etc/bird/bird.conf && install -m644 systemd/bird2-bgp-prefix-updater.service /etc/systemd/system/ && install -m644 systemd/bird2-bgp-prefix-updater.timer /etc/systemd/system/`.
3. Regenerate prefixes: `python3 /opt/bird2-bgp-prefix-updater/src/prefix_updater.py` (or wait for the timer).
4. Reload BIRD: `birdc configure`.
5. **Update downstream consumers** (Mikrotik / FRR / pfSense match rules): replace old IDs with the new ones from the mapping above. Anything matching `64888:101..112` must be re-mapped to the appropriate `2xx`/`3xx` ID. Anything matching `64888:103` (gov_networks) is now `64888:110` and belongs to the RU group.

## [3.1.0] - 2026-04-08
### Added
- Added download of AS53620 (Pinterest) prefixes via RIPEstat API (Community 111).
- Added download of AS54113 (Fastly CDN) prefixes via RIPEstat API (Community 112).
- Updated BIRD filters to support Community range 101..112.

## [3.0.0] - 2026-02-06
### Added
- **Per-source fallback resilience**: When a data source fails, old routes for that community are preserved from existing `prefixes.bird` instead of being deleted. Partial failures (some URLs work) don't trigger fallback.
- **Stale cache fallback**: If download fails after retries, script uses expired cache data (up to 7 days old) instead of returning empty results.
- **MY_AS auto-detection**: Script now automatically reads `MY_AS` from `/etc/bird/local-settings.conf` or `bird.conf`, eliminating need to set `LOCAL_AS` environment variable manually.
- **Improved logging**: New summary table showing per-source status (OK/FALLBACK), per-community breakdown, timing, and overall health.
- **Config split architecture**: `bird.conf` now uses includes for local settings and peers, allowing git-managed common config with local customizations that won't be overwritten.
  - `include "/etc/bird/local-settings.conf"` — router id, MY_AS, logging (not in git)
  - `include "/etc/bird/peers.d/*.conf"` — BGP peer definitions (not in git)
- Added example `conf/local-settings.conf.example` for reference.
- Exponential backoff on retries: 10s, 20s, 40s delays instead of fixed 10s.

### Changed
- **Cache moved to persistent directory**: `/var/lib/bird/prefix-cache/` instead of `/tmp/bird2-prefix-cache/` to survive reboots.
- **Cache TTL increased**: From 1 hour to 6 hours (configurable via `CACHE_TTL` env var).
- **Systemd service updated**: Script path changed from `/usr/local/bin/prefix_updater.py` to `/opt/bird2-bgp-prefix-updater/src/prefix_updater.py`. Removed hardcoded `LOCAL_AS=64888` (auto-detected now).
- **Download error handling**: `download_resource()` now returns `None` on error instead of `[]`, allowing distinction between failures and legitimately empty sources.
- BIRD config template (`conf/bird.conf`) now uses include structure and updated filter ranges to 101..110.
- Version 3.0.0.

### Fixed
- Filter ranges in `export_only_ru`, `export_blocked_lists`, `export_special_networks` updated from 101..109 to 101..110 to include Roblox (community 110).

## [2.9.0] - 2026-01-05
### Added
- Добавлено скачивание префиксов AS22697 (Roblox) через RIPEstat API (Community 110).
- Обновлены фильтры BIRD для поддержки диапазона Community 101..110.

### Changed
- Версия скрипта обновлена до 2.9.

## [2.8.0] - 2026-01-05
### Added
- Добавлено скачивание префиксов AS20940 (Akamai) через RIPEstat API (Community 109).
- Обновлены фильтры BIRD для поддержки диапазона Community 101..109.

### Changed
- Версия скрипта обновлена до 2.8.

## [2.7.0] - 2026-01-05
### Added
- Добавлено скачивание префиксов AS396986 (ByteDance) через RIPEstat API (Community 108).
- Поддержка локальных файлов в `prefix_updater.py` (добавлен `conf/custom.lst`).
- Улучшена обработка JSON в `prefix_updater.py` (поддержка `announced-prefixes`).
- Обновлены фильтры BIRD для поддержки диапазона Community 101..108.

### Changed
- Версия скрипта обновлена до 2.7.

## [2.6.0] - 2026-01-02
### Added
- Добавлены источники Stripe IP (API, Armada Gator, Webhooks) с Community 107.
- Обновлены фильтры BIRD для поддержки диапазона Community 101..107.

### Changed
- Версия скрипта обновлена до 2.6.

## [2.5.0] - 2026-01-01
### Added
- Добавлен список `ip.lst` как активный источник префиксов (Community 106).
- Добавлен закомментированный шаблон для списка `ipsum.lst` (Community 105).

### Changed
- Список `ipsmart.lst` (Community 101) деактивирован (закомментирован) по запросу.
- Версия скрипта обновлена до 2.5.

## [2.4.0] - 2025-12-31
### Added
- Встроенная диагностика: флаг `--check <IP/CIDR>` позволяет найти источник префикса во всех списках.
- Расширенная диагностика BIRD: теперь `--check` также выводит информацию о маршруте из внутренней таблицы BIRD (`birdc show route all`).
- Кэширование данных: скачанные списки кэшируются на 1 час для ускорения работы и диагностики.
- Поддержка аргументов командной строки через `argparse`.
- Флаг `--force-refresh` для принудительного игнорирования кэша.

### Changed
- Версия скрипта обновлена до 2.4.
- Улучшена справка по использованию внутри скрипта (`--help`).

## [2.3.0] - 2025-12-30
### Added
- Новый фильтр `export_comm101_105` в `bird.conf` для исключения российских префиксов (100) из списков блокировок (101-105).
- Зеркальная логика для `export_only_ru`: теперь российские префиксы, попавшие в списки блокировок, исключаются из чистого RU-экспорта.

### Changed
- Переименованы BGP Communities для соответствия новой терминологии:
  - `COMM_RU_MAINLAND` -> `COMM_RU_COMBINED` (100)
  - `COMM_AF_IPSUM` -> `COMM_BLOCKED_SMART` (101)
- Переход с `ipsum.lst` на более точный `ipsmart.lst` в `prefix_updater.py`.
  - `COMM_AF_SUBNETS` -> `COMM_RKN_SUBNETS` (102)
  - `COMM_CUSTOM_LISTS` -> `COMM_CUSTOM_USER` (104)
- Обновлены примеры фильтрации в `README.md` и `README_EN.md`.
