# BIRD2-BGP-Prefix-Updater (Multi-Source Aggregator)

[🇷🇺 Русский](README.md) · [🇬🇧 English](README_EN.md) · [itforprof.com](https://itforprof.com)

Автоматический агрегатор BGP-префиксов из нескольких источников (RIPEstat, Antifilter.network, Antifilter.download) с поддержкой BGP Community, автоматической оптимизацией (collapse) и отказоустойчивостью.

## Основные возможности
- **Отказоустойчивость**: При сбое источника сохраняются старые маршруты вместо их удаления
- **Резервный кэш**: Использование устаревшего кэша (до 7 дней) при недоступности источников
- **Автоопределение MY_AS**: Чтение номера AS из конфигурации BIRD автоматически
- **Разделение конфигурации**: `bird.conf` из git + локальные настройки в отдельных файлах
- **Улучшенное логирование**: Детальные таблицы статуса, разбивка по community, тайминг

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
  custom.lst                ← ваши кастомные IP
```

При `git pull` обновляется только `bird.conf` (фильтры, communities, шаблоны). Ваши локальные настройки и пиры не затрагиваются.

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
| **220** | **Blocked Sum** | Суммаризация списков (`ipsum.lst`, опционально) |
| **230** | **Blocked Smart** | Суммаризация РКН от /32 до /23 (`ipsmart.lst`, опционально) |

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

> Группы разделены так, чтобы простыми диапазонами community разводить разные категории по разным пирам. Например, `gov_networks` (110) — это российские госресурсы, и они логически в одной группе с RU Combined (100), а не в одном диапазоне с зарубежными блокировками.

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

## Примеры настройки клиентов (Mikrotik / WinBox)
В Routing -> Filters создайте правила на основе полученных community:

```shell
# Пример: направить заблокированные подсети РКН (210) в туннель
if (bgp-communities includes 64888:210) {
    set gw wg0;
    accept;
}
# Пример: игнорировать российские сети (100)
if (bgp-communities includes 64888:100) {
    reject;
}
```

## Диагностика и отладка
### Поиск источника префикса
Если вы обнаружили, что какой-то IP заблокирован или разрешен ошибочно, вы можете быстро найти, из какого списка он пришел:
```bash
/usr/local/bin/prefix_updater.py --check 194.67.72.31
```
Скрипт проверит все источники и выведет название списка, URL и присваиваемый Community ID.

### Кэширование
Скрипт кэширует скачанные списки в `/tmp/bird2-prefix-cache` на **1 час**. Это позволяет быстро проводить диагностику без повторного скачивания данных.
- Для принудительного обновления кэша используйте флаг `--force-refresh`:
  ```bash
  /usr/local/bin/prefix_updater.py --force-refresh
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
# Переустановите скрипт и юнит (если были изменения)
install -m755 src/prefix_updater.py /usr/local/bin/prefix_updater.py
systemctl daemon-reload
systemctl restart bird2-bgp-prefix-updater.service
```

[itforprof.com](https://itforprof.com) by Konstantin Tyutyunnik
