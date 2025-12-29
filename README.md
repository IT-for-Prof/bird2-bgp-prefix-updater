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
| **100** | **RU Mainland** | Все IPv4 сети РФ (из RIPEstat) |
| **101** | **AF Ipsum** | Суммаризация отдельных IP Antifilter по маске /24 |
| **102** | **AF Subnets** | Подсети из официальных списков Antifilter |
| **103** | **Gov Networks** | Сети государственных структур и ведомств |
| **104** | **Custom Lists** | **Telegram, Cloudflare, Google** и `custom.lst` Antifilter |
| **105** | **Reserved** | Зарезервировано для будущих нужд |

## Примеры фильтрации (BIRD2)

Вы можете использовать эти community для гибкой отдачи маршрутов разным клиентам. Примеры фильтров в `bird.conf`:

### Моно-фильтр (только один тип)
Отдавать только российские сети (community 100):
```bird
filter export_only_ru {
    if (MY_AS, 100) ~ bgp_community then accept;
    reject;
}
```

### Мульти-фильтр (диапазон)
Элегантный способ разрешить все спец-сети (101-104) одной строкой:
```bird
filter export_special_only {
    if (bgp_community ~ [(MY_AS, 101..104)]) then accept;
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

## Диагностика
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
