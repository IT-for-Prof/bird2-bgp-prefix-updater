# BIRD2-BGP-Prefix-Updater (EN)

Automates downloading, validating, and serving BGP prefixes from RIPEstat and various other sources (Antifilter, official service lists) using BIRD2.

## Features
- **Multi-Source**: Supports JSON (RIPEstat) and plain text (CIDR) lists.
- **Group Sources**: Easily aggregate multiple URLs (e.g., Telegram, Cloudflare) into a single BGP Community.
- **Auto-Collapse**: Automatically merges adjacent subnets to optimize route table size.
- **Atomic Updates**: Safe file writes with smoke testing before reloading BIRD.
- **IPv6 Safety**: Automatically ignores IPv6 for IPv4-only configurations.

## Requirements
- Linux (Debian/Ubuntu or RHEL/Alma/CentOS)
- BIRD v2/v3, Python 3

## Package installation
- Debian/Ubuntu:
  ```bash
  apt update && apt install -y bird2 python3
  ```
- RHEL/Alma/CentOS:
  ```bash
  dnf install -y epel-release && dnf install -y bird python3
  ```

## Project files
- `src/prefix_updater.py` — update script.
- `conf/bird.conf` — BIRD config template.
- `systemd/bird2-bgp-prefix-updater.service` — service unit.
- `systemd/bird2-bgp-prefix-updater.timer` — timer unit.
- Working files:
  - `/etc/bird/prefixes.bird` — include file for routes.
  - `/var/lib/bird/prefixes.txt` — canonical CIDR list.

## Quick start (via git clone)
```bash
cd /opt/
git clone https://github.com/IT-for-Prof/bird2-bgp-prefix-updater.git
cd bird2-bgp-prefix-updater
```

## Installation and placement

1. **Deploy project files:**
   ```bash
   install -m755 src/prefix_updater.py /usr/local/bin/prefix_updater.py
   install -m644 conf/bird.conf /etc/bird/bird.conf
   install -m644 systemd/bird2-bgp-prefix-updater.service /etc/systemd/system/
   install -m644 systemd/bird2-bgp-prefix-updater.timer /etc/systemd/system/
   ```

2. **Prepare directories and files:**
   ```bash
   mkdir -p /var/lib/bird
   touch /etc/bird/prefixes.bird
   chown bird:bird /etc/bird/prefixes.bird # For Debian/Ubuntu
   # or chown bird:bird /etc/bird/prefixes.bird for RHEL/Alma
   ```

3. **Configure BIRD:**
   Edit `/etc/bird/bird.conf` and replace `${ROUTER_ID}` and `${LOCAL_AS}` placeholders with your actual values (e.g., your public IP and AS number).

4. **Run initial prefix update:**
   It is recommended to run the script manually once before starting BIRD to generate the prefix file:
   ```bash
   /usr/local/bin/prefix_updater.py
   ```

5. **Enable and start services:**
   ```bash
   systemctl daemon-reload
   systemctl enable --now bird
   systemctl enable --now bird2-bgp-prefix-updater.timer
   ```

## BIRD configuration
Replace placeholders in `/etc/bird/bird.conf`:
- `${ROUTER_ID}` — router id IP.
- `${LOCAL_AS}` — your AS number.
- `${CLIENT_1_IP}`, `${CLIENT_1_AS}`, `${CLIENT_1_PASSWORD}` — client peers (examples commented).

Include file: `/etc/bird/prefixes.bird`. Table: `t_bgp_prefixes`.

## Changing country (RIPEstat)
No code edits required; override env var in the unit:
```bash
systemctl edit bird2-bgp-prefix-updater.service
[Service]
Environment="RIPESTAT_URL=https://stat.ripe.net/data/country-resource-list/data.json?resource=us"
systemctl daemon-reload
systemctl restart bird2-bgp-prefix-updater.service
```

## BGP Communities
Routes are tagged with the following communities (format `LOCAL_AS:ID`):

| ID | Name | Description |
| :--- | :--- | :--- |
| **100** | **RU Mainland** | All IPv4 networks of Russia (RIPEstat) |
| **101** | **AF Ipsum** | Antifilter's single IPs summarized by /24 |
| **102** | **AF Subnets** | Subnets from Antifilter's official lists |
| **103** | **Gov Networks** | Networks of government structures and agencies |
| **104** | **Custom Lists** | **Telegram, Cloudflare, Google** and Antifilter's `custom.lst` |
| **105** | **Reserved** | Reserved for future use |

## Filtering Examples (BIRD2)

### Only Russia (community 100)
```bird
filter export_only_ru {
    if (MY_AS, 100) ~ bgp_community then accept;
    reject;
}
```

### All special networks (range 101-104)
```bird
filter export_special_only {
    if (bgp_community ~ [(MY_AS, 101..104)]) then accept;
    reject;
}
```

### pfSense (FRR)
Config file `/var/etc/frr/frr.conf`:
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
Verification commands:
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

### Dynamic Neighbors (neighbor range)
To accept connections from any IP in a range:
```bird
protocol bgp any_client from t_client {
    neighbor range 0.0.0.0/0 as 64999;
    # NOTE: Password authentication is not supported 
    # for dynamic neighbors (neighbor range) in BIRD v2.
}
```

## Diagnostics

### BIRD (on server)
- **Status check**: `birdc show protocols`
- **View all routes in table**: `birdc "show route table t_bgp_prefixes"`
- **Route count**: `birdc "show route table t_bgp_prefixes count"`
- **Detailed info for a specific IP**: `birdc "show route for 77.88.44.242 table t_bgp_prefixes all"`
- **Force manual update**: `systemctl start bird2-bgp-prefix-updater.service`
- **Update logs**: `journalctl -u bird2-bgp-prefix-updater.service -f`
- **Timer status**: `systemctl list-timers bird2-bgp-prefix-updater.timer`

### Client (pfSense / FRR / Cisco)
- **General BGP status**: `vtysh -c "show bgp summary"` or `vtysh -c "show bgp ipv4 unicast summary"`
- **View received routes**: `vtysh -c "show bgp ipv4 unicast"`
- **Routes from a specific neighbor**: `vtysh -c "show bgp ipv4 unicast neighbors <BIRD_IP> received-routes"`
- **Check first lines of the table**: `vtysh -c "show bgp ipv4 unicast | head"`

## Security
- **Firewall**: Restrict TCP/179 to trusted client IPs only.
  - **iptables**:
    ```bash
    # Allow incoming BGP from a specific neighbor
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
- **Passwords (MD5)**: Use MD5 authentication for BGP sessions. The password must match on both sides.
  - In BIRD config: `password "your_password";`
  - In client settings: look for "password", "tcp-md5-key", or "secret" fields.
- Export limit `20000` is set to protect clients from route table overflow.

itforprof.com by Konstantin Tyutyunnik

