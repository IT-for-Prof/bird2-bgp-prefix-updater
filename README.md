# BIRD2-BGP-Prefix-Updater (Multi-Source Aggregator)

[🇷🇺 Русский](README.md) · [🇬🇧 English](README_EN.md) · [itforprof.com](https://itforprof.com)

Автоматический агрегатор BGP-префиксов из нескольких источников (RIPEstat, Antifilter.network, Antifilter.download) с поддержкой BGP Community, автоматической оптимизацией (collapse) и отказоустойчивостью.

## Основные возможности
- **Отказоустойчивость**: При сбое источника сохраняются старые маршруты вместо их удаления
- **Резервный кэш**: Использование устаревшего кэша (до 7 дней) при недоступности источников
- **Автоопределение MY_AS**: Чтение номера AS из конфигурации BIRD автоматически
- **Разделение конфигурации**: `bird.conf` из git + локальные настройки в отдельных файлах
- **Улучшенное логирование**: Детальные таблицы статуса, разбивка по community, тайминг
- **Строгая IPv4-валидация**: Некорректные IPv4/CIDR формы не принимаются как legacy shorthand
- **Цельные multi-AS группы**: Netflix и YouTube обновляются только если все обязательные RIPEstat AS-источники доступны; иначе сохраняются старые маршруты community

## Требования
- Linux (Debian/Ubuntu или RHEL/Alma/CentOS).
- BIRD v2/v3, Python 3.

## Установка пакетов
- Debian/Ubuntu:
  ```bash
  apt update && apt install -y bird2 python3
  ```
- RHEL/Alma/CentOS:
  ```bash
  dnf install -y epel-release && dnf install -y bird python3
  ```

## Файлы проекта
- `src/prefix_updater.py` — скрипт агрегации.
- `conf/bird.conf` — шаблон конфигурации BIRD.
- `conf/custom.lst` — комментированный шаблон для локальных IPv4-префиксов.
- `systemd/bird2-bgp-prefix-updater.service` — юнит сервиса.
- `systemd/bird2-bgp-prefix-updater.timer` — юнит таймера.
- Рабочие файлы:
  - `/etc/bird/prefixes.bird` — сгенерированный файл маршрутов с community.
  - `/var/lib/bird/prefixes.txt` — чистый список CIDR (для отладки).

## Быстрый старт (через git clone)
```bash
cd /opt/
git clone https://github.com/IT-for-Prof/bird2-bgp-prefix-updater.git
cd bird2-bgp-prefix-updater
```

## Установка и размещение файлов

1. **Установите файлы проекта:**
   ```bash
   # Скопируйте BIRD config (общий, из git)
   install -m644 conf/bird.conf /etc/bird/bird.conf
   install -m644 conf/custom.lst /etc/bird/custom.lst

   # Systemd сервис и таймер
   install -m644 systemd/bird2-bgp-prefix-updater.service /etc/systemd/system/
   install -m644 systemd/bird2-bgp-prefix-updater.timer /etc/systemd/system/
   ```

2. **Создайте локальные настройки (не в git):**
   ```bash
   # Создайте local-settings.conf с вашими параметрами
   cat > /etc/bird/local-settings.conf <<'EOF'
   log syslog all;
   router id 10.0.0.1;           # Ваш router ID
   define MY_AS = 65000;         # Ваш AS номер
   EOF

   # Создайте директорию для пиров
   mkdir -p /etc/bird/peers.d
   ```

3. **Подготовьте рабочие директории:**
   ```bash
   mkdir -p /var/lib/bird /var/lib/bird/prefix-cache
   touch /etc/bird/prefixes.bird
   chown bird:bird /etc/bird/prefixes.bird # Для Debian/Ubuntu
   ```

4. **Добавьте BGP пиры** (примеры в `/etc/bird/peers.d/`):
   ```bash
   cat > /etc/bird/peers.d/my_peer.conf <<'EOF'
   protocol bgp my_peer from t_client {
       neighbor 192.0.2.2 as 65002;
       ipv4 { export filter export_only_ru; };
   }
   EOF
   ```

5. **Запустите обновление:**
   ```bash
   # Скрипт автоматически определит MY_AS из local-settings.conf
   python3 /opt/bird2-bgp-prefix-updater/src/prefix_updater.py

   systemctl daemon-reload
   systemctl enable --now bird
   systemctl enable --now bird2-bgp-prefix-updater.timer
   ```

### Структура файлов `/etc/bird/`
```
/etc/bird/
  bird.conf                 ← из git (общая конфигурация)
  local-settings.conf       ← ваши настройки (router id, MY_AS, logging)
  peers.d/*.conf            ← ваши BGP пиры (не перезаписываются)
  prefixes.bird             ← автогенерация скриптом
  custom.lst                ← ваши кастомные IP (изначально комментированный шаблон)
```

При `git pull` меняется только копия репозитория в `/opt/bird2-bgp-prefix-updater`.
Файлы `/etc/bird/local-settings.conf` и `/etc/bird/peers.d/*.conf` не хранятся в репозитории и не перезаписываются.
Переустанавливайте `conf/bird.conf` и systemd-юниты только когда хотите применить обновлённые шаблоны из git.

## Конфигурация BIRD и переменные окружения

Сгенерированный include-файл: `/etc/bird/prefixes.bird`. Маршруты загружаются в таблицу `t_bgp_prefixes`.

| Настройка | Значение по умолчанию | Назначение |
| :--- | :--- | :--- |
| `MY_AS` в `/etc/bird/local-settings.conf` | fallback `64888` | AS для BGP community |
| `LOCAL_AS` env | не задано | Переопределяет автоопределение `MY_AS` |
| `OUTPUT_BIRD` | `/etc/bird/prefixes.bird` | Генерируемые static routes для BIRD |
| `OUTPUT_TXT` | `/var/lib/bird/prefixes.txt` | Генерируемый plain CIDR список |
| `BIRD_CONF` | `/etc/bird/bird.conf` | Конфиг для smoke-test и автоопределения AS |
| `CACHE_DIR` | `/var/lib/bird/prefix-cache` | Каталог кэша загрузок |
| `CACHE_TTL` | `21600` | Время жизни свежего кэша в секундах |
| `STALE_CACHE_MAX_AGE` | `604800` | Максимальный возраст stale cache при сбоях загрузки |

## BGP Communities

Маршруты помечаются community в формате `LOCAL_AS:ID`. ID разбиты на семантические группы по сотням:

| Диапазон | Назначение |
| :--- | :--- |
| **100..199** | Российские ресурсы — обычно маршрутизируются через локальный канал |
| **200..299** | Заблокированные РКН подсети — маршрутизируются в обход блокировок |
| **300..399** | Зарубежные сервисы — также обычно маршрутизируются в обход блокировок |

### Российские ресурсы (100..199)
| ID | Название | Описание |
| :--- | :--- | :--- |
| **100** | **RU Combined** | Все IPv4 сети РФ (из RIPEstat) |
| **110** | **Gov Networks** | Сети госструктур и ведомств (`govno.lst`) |

### Заблокированные РКН подсети (200..299)
| ID | Название | Описание |
| :--- | :--- | :--- |
| **200** | **Blocked IP** | Список IP (`ip.lst`) Antifilter |
| **210** | **RKN Subnets** | Подсети из официальных списков Antifilter |

### Зарубежные сервисы (300..399)
| ID | Название | Описание |
| :--- | :--- | :--- |
| **300** | **Official Services** | **Telegram, Cloudflare, Google** и локальный `custom.lst` |
| **310** | **Custom User** | `custom.lst` от Antifilter |
| **320** | **Stripe** | Сети Stripe (API, Webhooks, etc) |
| **330** | **ByteDance** | Префиксы AS396986 (ByteDance) |
| **340** | **Akamai** | Префиксы AS20940 (Akamai) |
| **350** | **Roblox** | Префиксы AS22697 (Roblox) |
| **360** | **Pinterest** | Префиксы AS53620 (Pinterest) |
| **370** | **Fastly** | Префиксы AS54113 (Fastly CDN) |
| **380** | **Meta** | Префиксы AS32934 (Meta/Facebook) |
| **381** | **Twitter/X** | Префиксы AS13414 (Twitter/X) |
| **382** | **Netflix** | Префиксы AS2906 и AS40027 (Netflix); оба RIPEstat источника обязательны |
| **383** | **AWS CloudFront** | IPv4-префиксы AWS `CLOUDFRONT` из `ip-ranges.json`; это фильтрованный список CloudFront, не весь AWS |
| **386** | **YouTube** | Префиксы AS36040 и AS43515 (YouTube); оба RIPEstat источника обязательны |

> Группы разделены так, чтобы простыми диапазонами community разводить разные категории по разным пирам. Например, `gov_networks` (110) — это российские госресурсы, и они логически в одной группе с RU Combined (100), а не в одном диапазоне с зарубежными блокировками.

### Примечания по источникам
- `ru_combined` использует RIPEstat `country-resource-list`, который возвращает ASN, IPv4 ranges/prefixes и IPv6 prefixes для страны: <https://stat-ui.stat.ripe.net/docs/data-api/api-endpoints/country-resource-list>
- AS-источники сервисов используют RIPEstat `announced-prefixes`, который возвращает анонсируемые префиксы для заданного ASN: <https://stat-ui.stat.ripe.net/docs/data-api/api-endpoints/announced-prefixes>
- `aws_networks` использует AWS `ip-ranges.json`, читает только `prefixes[].ip_prefix`, игнорирует `ipv6_prefixes` и по умолчанию фильтрует только сервис `CLOUDFRONT`: <https://ip-ranges.amazonaws.com/ip-ranges.json>
- `rkn_subnets` использует два mirror URL и допускает частичный успех. Netflix и YouTube состоят из нескольких AS-источников и обновляют community только если все URL успешно обработаны.
- `official_services` объединяет Telegram, Cloudflare, Google и локальный `/etc/bird/custom.lst` в community `300`; remote `custom.lst` от Antifilter остаётся отдельной community `310`.

### Изменение AWS-фильтра
Чтобы добавить другой AWS-сервис, отредактируйте `aws_services` у источника `aws_networks` в `src/prefix_updater.py`, например:
```python
"aws_services": ["CLOUDFRONT", "GLOBALACCELERATOR"],
```
Не очищайте фильтр без отдельной проверки: весь список AWS намного шире CloudFront и может сильно изменить маршрутизацию.

## Примеры фильтрации (BIRD2)

Благодаря группировке по сотням фильтры читаются как естественный язык:

### Только российские ресурсы (RU Combined + Gov Networks)
Для пиров, через которых должны идти только российские сети:
```bird
filter export_only_ru {
    if (bgp_community ~ [(MY_AS, 100..199)]) then accept;
    reject;
}
```

### Только блокировки и зарубежные сервисы (без РФ)
Для пиров, через которых надо обходить блокировки, но не нужны российские префиксы:
```bird
filter export_blocked_lists {
    if (bgp_community ~ [(MY_AS, 200..399)]) then accept;
    reject;
}
```

### Только заблокированные подсети РКН (без зарубежных сервисов)
```bird
filter export_blocked_only {
    if (bgp_community ~ [(MY_AS, 200..299)]) then accept;
    reject;
}
```

### Только зарубежные сервисы (без списков РКН)
```bird
filter export_services_only {
    if (bgp_community ~ [(MY_AS, 300..399)]) then accept;
    reject;
}
```

## Настройка клиента MikroTik RouterOS 7

Пример настройки клиента, который получает префиксы от BIRD и заворачивает трафик через нужный шлюз. Фильтрация по типу трафика (RU / блокировки / зарубежные сервисы) задаётся на стороне BIRD через `export filter` в `peers.d/`.

**Плейсхолдеры (замените на свои):**

| Плейсхолдер | Что это |
|---|---|
| `BIRD_IP` | Адрес BIRD-сервера (публичный или приватный — неважно) |
| `MY_ROUTER_ID` | Router-ID MikroTik, любой уникальный IPv4 |
| `GW_ADDR` | Шлюз, через который пойдёт трафик (IP VPN-туннеля, ZeroTier, физического интерфейса и т.п.) |
| `LOCAL_AS` | AS клиента (см. `peers.d/*.conf` на сервере) |
| `REMOTE_AS` | AS сервера BIRD (`MY_AS` из `local-settings.conf`) |

> `BIRD_IP` и `GW_ADDR` — это **разные сети**. BGP-сессия может идти через один канал (например интернет), а трафик по полученным маршрутам — через другой (VPN-туннель).

> **Динамический клиент:** если MikroTik не имеет статического адреса — на стороне BIRD используйте `neighbor range X.X.X.X/Y as ... ; dynamic name "...";` (см. пример в `peers.d/LAN.conf`).

### 1. BGP-соединение

```shell
/routing bgp connection
add name=bird-server \
    as=LOCAL_AS \
    router-id=MY_ROUTER_ID \
    local.role=ebgp \
    remote.address=BIRD_IP/32 \
    remote.as=REMOTE_AS \
    multihop=yes \
    connect=yes listen=no \
    input.filter=bgp-in \
    input.ignore-as-path-len=yes \
    output.filter-chain=discard \
    routing-table=main
```

| Параметр | Зачем |
|---|---|
| `multihop=yes` | BIRD настроен с `multihop` — между ними может быть несколько хопов |
| `connect=yes listen=no` | MikroTik инициирует соединение, BIRD пассивный (`passive on`) |
| `output.filter-chain=discard` | Не анонсировать маршруты обратно в BIRD |
| `input.ignore-as-path-len=yes` | Обход проверки AS-path при multihop |

### 2. Фильтры маршрутов

```shell
/routing filter rule
# Цепочка discard — отбрасывает всё (используется в output.filter-chain выше)
add chain=discard rule="reject;"

# Цепочка bgp-in — обрабатывает входящие маршруты от BIRD
# Защита: не перехватывать сам BGP-пир
add chain=bgp-in rule="if (dst in BIRD_IP/32) { reject; }"

# Все полученные маршруты — через нужный шлюз
add chain=bgp-in rule="set gw GW_ADDR; accept;"

# Запрет по умолчанию
add chain=bgp-in rule="reject;"
```

`GW_ADDR` может быть IP-адресом или именем интерфейса (`wg-tunnel`, `gre-tunnel1`, `zerotier1`).

### 3. Маршрут до шлюза (опционально)

Если `GW_ADDR` сам доступен только через какой-то интерфейс/туннель и автоматически не резолвится — добавьте статический маршрут:

```shell
/ip route
add dst-address=GW_ADDR/32 gateway=<your-tunnel-iface-or-ip> check-gateway=ping
```

### 4. Проверка

```shell
# Состояние BGP-сессии (должна быть established)
/routing bgp session print

# Количество принятых маршрутов
/ip route print count-only where bgp

# Конкретный маршрут
/ip route print where dst-address="149.154.160.0/20"
```

## Диагностика и отладка
### Поиск источника префикса
Если вы обнаружили, что какой-то IP заблокирован или разрешен ошибочно, вы можете быстро найти, из какого списка он пришел:
```bash
python3 /opt/bird2-bgp-prefix-updater/src/prefix_updater.py --check 194.67.72.31
python3 /opt/bird2-bgp-prefix-updater/src/prefix_updater.py --check 3.10.17.128/25
```
Скрипт проверит все источники и выведет название списка, URL и присваиваемый Community ID.

### Кэширование
Скрипт кэширует скачанные списки в `/var/lib/bird/prefix-cache` на **6 часов** (`CACHE_TTL`). При сбое источника используется устаревший кэш до 7 дней (`STALE_CACHE_MAX_AGE`). Оба значения можно переопределить через переменные окружения.
- Для принудительного обновления кэша используйте флаг `--force-refresh`:
  ```bash
  python3 /opt/bird2-bgp-prefix-updater/src/prefix_updater.py --force-refresh
  ```

### Общие команды
- **Статус BGP**: `birdc show protocols`
- **Проверка community у маршрута**: `birdc "show route table t_bgp_prefixes all"`
- **Логи обновления**: `journalctl -u bird2-bgp-prefix-updater.service -f`

## Обновление проекта
Если вы хотите обновить скрипт до последней версии из репозитория:
```bash
cd /opt/bird2-bgp-prefix-updater
git pull
# Сервис запускает скрипт напрямую из этого каталога — копировать не нужно.
# Если менялся systemd-юнит или bird.conf — переустановите их:
install -m644 systemd/bird2-bgp-prefix-updater.service /etc/systemd/system/
install -m644 systemd/bird2-bgp-prefix-updater.timer /etc/systemd/system/
# Внимание: bird.conf перезапишет ваши изменения, если вы редактировали его локально
install -m644 conf/bird.conf /etc/bird/bird.conf
systemctl daemon-reload
systemctl restart bird2-bgp-prefix-updater.service
birdc configure
```

[itforprof.com](https://itforprof.com) by Konstantin Tyutyunnik
