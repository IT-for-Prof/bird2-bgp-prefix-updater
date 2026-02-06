# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Поддержка локальных файлов в `prefix_updater.py` (добавлен `conf/custom.lst` для IP LastPass).
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

