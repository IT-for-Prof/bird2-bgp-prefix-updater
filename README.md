# BIRD2-BGP-Prefix-Updater (Multi-Source Aggregator)

Автоматический агрегатор BGP-префиксов из нескольких источников (RIPEstat, Antifilter.network, Antifilter.download) с поддержкой BGP Community и автоматической оптимизацией (collapse).

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

1. **Разместите файлы проекта:**
   ```bash
   install -m755 src/prefix_updater.py /usr/local/bin/prefix_updater.py
   install -m644 conf/bird.conf /etc/bird/bird.conf
   install -m644 conf/custom.lst /etc/bird/custom.lst
   install -m644 systemd/bird2-bgp-prefix-updater.service /etc/systemd/system/
   install -m644 systemd/bird2-bgp-prefix-updater.timer /etc/systemd/system/
   ```

2. **Подготовьте рабочие директории:**
   ```bash
   mkdir -p /var/lib/bird
   touch /etc/bird/prefixes.bird
   chown bird:bird /etc/bird/prefixes.bird # Для Debian/Ubuntu
   ```

3. **Настройте BIRD:**
   Отредактируйте `/etc/bird/bird.conf` и замените `${ROUTER_ID}` на ваш IP, а `${LOCAL_AS}` на номер вашей автономной системы.

4. **Настройте LOCAL_AS в сервисе:**
   ```bash
   systemctl edit bird2-bgp-prefix-updater.service
   # Добавьте ваш номер AS (по умолчанию 64888):
   [Service]
   Environment="LOCAL_AS=64888"
   ```

5. **Запустите обновление:**
   ```bash
   /usr/local/bin/prefix_updater.py
   systemctl daemon-reload
   systemctl enable --now bird
   systemctl enable --now bird2-bgp-prefix-updater.timer
   ```

## BGP Communities
Скрипт помечает маршруты следующими community (формат `LOCAL_AS:ID`):

| ID | Название | Описание |
| :--- | :--- | :--- |
| **100** | **RU Combined** | Все IPv4 сети РФ (из RIPEstat) |
| **101** | **Blocked Smart** | Суммаризация списков РКН по сетям от /32 до /23 (`ipsmart.lst`) |
| **102** | **RKN Subnets** | Подсети из официальных списков Antifilter |
| **103** | **Gov Networks** | Сети государственных структур и ведомств |
| **104** | **Custom User** | **Telegram, Cloudflare, Google** и `custom.lst` Antifilter |
| **105** | **Reserved** | Зарезервировано для будущих нужд |
| **106** | **Blocked IP** | Список IP (`ip.lst`) Antifilter |
| **107** | **Stripe IP** | Сети Stripe (API, Webhooks, etc) |
| **108** | **ByteDance** | Префиксы AS396986 (ByteDance) |
| **109** | **Akamai** | Префиксы AS20940 (Akamai) |
| **110** | **Roblox** | Префиксы AS22697 (Roblox) |

## Примеры фильтрации (BIRD2)

Вы можете использовать эти community для гибкой отдачи маршрутов разным клиентам. Примеры фильтров в `bird.conf`:

### Моно-фильтр (только один тип)
Отдавать российские сети (community 100), исключая те, что попали в списки блокировок (101-110):
```bird
filter export_only_ru {
    if (bgp_community ~ [(MY_AS, 101..110)]) then reject;
    if (COMM_RU_COMBINED ~ bgp_community) then accept;
    reject;
}
```

### Исключение пересечений (RU vs Blocked)
Если префикс одновременно является и российским (100), и заблокированным (101-110), данные фильтры гарантируют отдачу только в один конкретный пиринг:

1. **Только чистый RU** (без заблокированных префиксов):
```bird
filter export_only_ru {
    if (bgp_community ~ [(MY_AS, 101..110)]) then reject;
    if (COMM_RU_COMBINED ~ bgp_community) then accept;
    reject;
}
```

2. **Только блокировки** (без российских префиксов):
```bird
filter export_comm101_110 {
    if (COMM_RU_COMBINED ~ bgp_community) then reject;
    if (bgp_community ~ [(MY_AS, 101..110)]) then accept;
    reject;
}
```

### Мульти-фильтр (диапазон)
Элегантный способ разрешить все спец-сети (101-110) одной строкой без дополнительных проверок:
```bird
filter export_special_only {
    if (bgp_community ~ [(MY_AS, 101..110)]) then accept;
    reject;
}
```

## Примеры настройки клиентов (Mikrotik / WinBox)
В Routing -> Filters создайте правила на основе полученных community:

```shell
# Пример: направить заблокированные подсети (101) в туннель
if (bgp-communities includes 64888:101) {
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

itforprof.com by Konstantin Tyutyunnik
