# Continuity Ledger

## Goal
Сборка и развертывание универсального BGP route-server (BIRD v2/v3) с автоматическим обновлением IPv4 префиксов из RIPEstat (любой регион) и раздачей их клиентам.

## Constraints/Assumptions
- ОС: Linux (AlmaLinux, Debian, etc.).
- Демон: BIRD v2/v3.
- Язык: Python 3.6+ (stdlib + typing для совместимости).
- Обновление: 1 раз в сутки через systemd timer.
- Атомарность: Обновление файлов через tmp + rename.

## Key decisions
- Протокол `static` BIRD читает `/etc/bird/prefixes.bird` в таблицу `t_bgp_prefixes`.
- Маршруты устанавливаются как `blackhole`, чтобы сервер не стал транзитным.
- Python-скрипт `prefix_updater.py` (stdlib) с retry, collapse и atomic write.
- Универсальный `RIPESTAT_URL` задается через переменную окружения в systemd unit.
- Конфигурация BIRD содержит плейсхолдеры `${ROUTER_ID}` и `${LOCAL_AS}`, которые должны быть заменены пользователем ПЕРЕД запуском.
- Скрипт `prefix_updater.py` следует запустить вручную один раз перед стартом BIRD для генерации `prefixes.bird`.
- Использование модуля `typing` для обеспечения совместимости с версиями Python ниже 3.9.

## State
- [x] Выбор и обоснование демона
- [x] Основной конфиг BIRD v2/v3 (template) с примерами статического и динамического соседей
- [x] Python3 скрипт обновления префиксов (stdlib + compatibility fix)
- [x] Systemd Service & Timer
- [x] Инструкция по эксплуатации (обновлена: диагностика для BIRD и vtysh/FRR)
- [x] Тест-план
- [x] Анализ и исправление ошибки запуска BIRD (плейсхолдеры).
- [x] Исправление ошибки совместимости Python.
- [x] Сброс истории Git и создание нового Initial commit.

## Done
- В `README.md` и `README_EN.md` расширен раздел "Диагностика":
  - Добавлены команды BIRD для просмотра таблицы и проверки конкретных IP.
  - Добавлены команды `vtysh` для клиентов (FRR/Cisco) для проверки статуса и полученных маршрутов.
- История Git сброшена, создан новый "Initial commit" в ветке `main` на GitHub.

## Now
- Задача завершена.

## Next
- Проверка чистоты репозитория.

## Open questions
- Нет.

## Working set
- conf/bird.conf
- README.md
- README_EN.md
- src/prefix_updater.py
- CONTINUITY.md
