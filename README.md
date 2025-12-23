# BIRD2-BGP-Prefix-Updater (RU)

Автоматическое обновление и раздача BGP-префиксов из RIPEstat с помощью BIRD2. Скрипт универсален и может работать с любой страной через переменную `RIPESTAT_URL`.

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
- `src/prefix_updater.py` — скрипт обновления.
- `conf/bird.conf` — шаблон конфигурации BIRD.
- `systemd/bird2-bgp-prefix-updater.service` — юнит сервиса.
- `systemd/bird2-bgp-prefix-updater.timer` — юнит таймера.
- Рабочие файлы:
  - `/etc/bird/prefixes.bird` — include-файл маршрутов.
  - `/var/lib/bird/prefixes.txt` — канонический список CIDR.

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

2. **Подготовьте рабочие директории и файлы:**
   ```bash
   mkdir -p /var/lib/bird
   touch /etc/bird/prefixes.bird
   chown bird:bird /etc/bird/prefixes.bird # Для Debian/Ubuntu
   # или chown bird:bird /etc/bird/prefixes.bird для RHEL/Alma
   ```

3. **Настройте BIRD:**
   Отредактируйте `/etc/bird/bird.conf` и замените плейсхолдеры `${ROUTER_ID}` и `${LOCAL_AS}` на ваши реальные значения (например, ваш публичный IP и номер AS).

4. **Запустите обновление префиксов:**
   Перед запуском BIRD рекомендуется один раз запустить скрипт вручную, чтобы сгенерировать файл префиксов:
   ```bash
   /usr/local/bin/prefix_updater.py
   ```

5. **Активируйте сервисы:**
   ```bash
   systemctl daemon-reload
   systemctl enable --now bird
   systemctl enable --now bird2-bgp-prefix-updater.timer
   ```

## Настройка BIRD
В `/etc/bird/bird.conf` необходимо заменить:
- `${ROUTER_ID}` — IP для router id.
- `${LOCAL_AS}` — ваш AS.
- `${CLIENT_1_IP}`, `${CLIENT_1_AS}`, `${CLIENT_1_PASSWORD}` — для клиентов (примеры закомментированы).

Файл include: `/etc/bird/prefixes.bird` (генерируется скриптом). Таблица: `t_bgp_prefixes`.

## Смена страны (RIPEstat)
Меняется без правки кода, через переменную окружения в unit-файле:
```bash
systemctl edit bird2-bgp-prefix-updater.service
# Добавьте:
[Service]
Environment="RIPESTAT_URL=https://stat.ripe.net/data/country-resource-list/data.json?resource=us"
systemctl daemon-reload
systemctl restart bird2-bgp-prefix-updater.service
```

## Примеры настройки клиентов

### BIRD2
```bird
protocol bgp rs from t_client {
    neighbor 192.0.2.1 as 65001;
    # password "md5secret";
}
```

### pfSense (FRR)
Конфигурация `/var/etc/frr/frr.conf`:
```
!
router bgp 64999
 bgp log-neighbor-changes
 no bgp network import-check
 neighbor <BIRD_IP> remote-as 65000
 neighbor <BIRD_IP> description RS-SERVER
 neighbor <BIRD_IP> ebgp-multihop 255
 !
 address-family ipv4 unicast
  neighbor <BIRD_IP> activate
  no neighbor <BIRD_IP> send-community
  neighbor <BIRD_IP> route-map PERMIT-ALL in
 exit-address-family
 !
```
Команды для проверки:
```bash
vtysh -c "show bgp summary"
vtysh -c "show bgp ipv4 unicast neighbors <BIRD_IP> received-routes"
vtysh -c "show bgp ipv4 unicast | head"
```

### Cisco / Quagga / FRR (Generic)
```
router bgp 65001
  neighbor <BIRD_IP> remote-as 65000
  neighbor <BIRD_IP> ebgp-multihop 2
```

### MikroTik
```
/routing bgp connection add name=rs remote.address=<BIRD_IP> remote.as=65000 \
    local.address=<YOUR_IP> multihop=yes
```

### Динамические клиенты (neighbor range)
Для приема соединений от любого IP из диапазона:
```bird
protocol bgp any_client from t_client {
    neighbor range 0.0.0.0/0 as 64999;
    # ПРИМЕЧАНИЕ: Для динамических соседей (neighbor range) в BIRD v2 
    # аутентификация (password) не поддерживается.
}
```

## Диагностика

### BIRD (на сервере)
- **Проверка статуса**: `birdc show protocols`
- **Просмотр всех маршрутов в таблице**: `birdc "show route table t_bgp_prefixes"`
- **Количество маршрутов**: `birdc "show route table t_bgp_prefixes count"`
- **Детальная информация по конкретному IP**: `birdc "show route for 77.88.44.242 table t_bgp_prefixes all"`
- **Принудительный запуск обновления**: `systemctl start bird2-bgp-prefix-updater.service`
- **Логи обновления**: `journalctl -u bird2-bgp-prefix-updater.service -f`
- **Проверка таймера**: `systemctl list-timers bird2-bgp-prefix-updater.timer`

### Клиент (pfSense / FRR / Cisco)
- **Общий статус BGP**: `vtysh -c "show bgp summary"` или `vtysh -c "show bgp ipv4 unicast summary"`
- **Просмотр полученных маршрутов**: `vtysh -c "show bgp ipv4 unicast"`
- **Маршруты от конкретного соседа**: `vtysh -c "show bgp ipv4 unicast neighbors <BIRD_IP> received-routes"`
- **Проверка первых строк таблицы**: `vtysh -c "show bgp ipv4 unicast | head"`

## Безопасность
- **Firewall**: Ограничьте доступ к TCP/179 только для клиентов.
  - **iptables**:
    ```bash
    # Разрешить входящий BGP от конкретного соседа
    iptables -A INPUT -p tcp -s 1.2.3.4 --dport 179 -j ACCEPT
    ```
  - **nftables**:
    ```bash
    nft add rule inet filter input ip saddr 1.2.3.4 tcp dport 179 accept
    ```
  - **ufw** (Ubuntu/Debian):
    ```bash
    ufw allow from 1.2.3.4 to any port 179 proto tcp
    ```
  - **firewalld** (RHEL/AlmaLinux):
    ```bash
    firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="1.2.3.4" port protocol="tcp" port="179" accept'
    firewall-cmd --reload
    ```
- **Пароли (MD5)**: Используйте MD5-пароли для защиты BGP-сессий. Пароль должен совпадать на обеих сторонах.
  - В конфиге BIRD: `password "ваш_пароль";`
  - В настройках клиента: соответствующее поле "password", "tcp-md5-key" или "secret".
- В конфиге установлен лимит `export limit 20000` для защиты клиентов от переполнения таблицы маршрутов.

itforprof.com by Konstantin Tyutyunnik

