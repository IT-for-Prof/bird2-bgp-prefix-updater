# Continuity Ledger

## Goal
Сборка и развертывание универсального BGP route-server (BIRD v2/v3) с автоматической агрегацией IPv4 префиксов из множества источников (RIPEstat, Antifilter) и раздачей их клиентам с использованием BGP Community.

## Constraints/Assumptions
- ОС: Linux (AlmaLinux, Debian, etc.).
- Демон: BIRD v2/v3.
- Язык: Python 3.6+ (stdlib + typing для совместимости).
- Обновление: через systemd timer.
- Атомарность: Обновление файлов через tmp + rename.
- Валидация: Smoke-тест через `bird -p -c` перед применением конфига.

## Key decisions
- Переход на мульти-источники (агрегатор): RIPEstat, Antifilter.network, Antifilter.download.
- Использование BGP Community (100-105) для классификации маршрутов (RU, Blocked, Subnets, Gov, Custom).
- Включение списков `ipsum.lst` (/24) для полного охвата заблокированных ресурсов.
- Автоматическое объединение (collapse) пересекающихся и смежных префиксов.
- `LOCAL_AS` вынесен в переменную окружения systemd для глобального управления community.
- Лимит экспорта увеличен до 100,000 для предотвращения разрывов сессий при больших списках.
- **Исправление формата community**: переход от `bgp_community.add([(...)])` к `bgp_community.add((ASN, VAL))`.
- **Поддержка нескольких community**: генерация нескольких последовательных вызовов `.add()`.
- **Атомарная запись с валидацией**: использование временного конфига и `bird -p -c` для проверки синтаксиса перед перезаписью.

## State
- [x] Выбор и обоснование демона
- [x] Основной конфиг BIRD v2/v3 (агрегатор с поддержкой community)
- [x] Python3 скрипт агрегации (мульти-источники, collapse, community)
- [x] Systemd Service & Timer (с поддержкой LOCAL_AS)
- [x] Инструкция по эксплуатации (BGP Community, Mikrotik)
- [x] Тест-план
- [x] Исправление бага с community и добавление smoke-теста

## Done
- Реализован мульти-источник агрегатор в `src/prefix_updater.py`.
- Добавлена поддержка BGP Community для гибкой фильтрации на стороне клиента.
- Настроен `bird.conf` для работы с расширенными списками (hold timer, export limit).
- Обновлен `README.md` с описанием community и примерами для Mikrotik.
- **v2.1**: Исправлен формат `bgp_community.add`. Добавлен self-check и smoke-тест через `bird -p`.
- **v2.2**: Добавлены расширенные примеры фильтрации (community 100, 101-105) в `bird.conf` и `README.md`.
- **v2.3.0**: Улучшена безопасность фильтров (замена сетов на индивидуальные проверки). Добавлена явная версионность в скрипт (`--version`) и документацию.

## Now
- Задача по исправлению генерации и добавлению валидации выполнена.

## Next
- Проверка работоспособности на реальных данных.

## Open questions
- Нет.

## Working set
- conf/bird.conf
- README.md
- src/prefix_updater.py
- CONTINUITY.md
- systemd/bird2-bgp-prefix-updater.service
