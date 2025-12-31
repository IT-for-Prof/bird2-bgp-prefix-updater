# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.4.0] - 2025-12-31
### Added
- Встроенная диагностика: флаг `--check <IP/CIDR>` позволяет найти источник префикса во всех списках.
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

