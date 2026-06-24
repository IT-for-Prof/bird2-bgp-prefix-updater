# BIRD2-BGP-Prefix-Updater (EN)

[🇷🇺 Русский](README.md) · [🇬🇧 English](README_EN.md) · [itforprof.com](https://itforprof.com)

Automates downloading, validating, and serving BGP prefixes from RIPEstat and various other sources (Antifilter, official service lists) using BIRD2 with built-in resilience and error handling.

## Features
- **Per-Source Fallback**: When a data source fails, old routes for that community are preserved instead of being deleted
- **Stale Cache Fallback**: Uses expired cache (up to 7 days old) when downloads fail after retries
- **MY_AS Auto-Detection**: Automatically reads AS number from BIRD config, no manual environment variable needed
- **Config Split Architecture**: Git-managed common config + local settings in separate includes that won't be overwritten
- **Improved Logging**: Detailed status tables, per-community breakdown, timing, and health indicators
- **Multi-Source**: Supports JSON (RIPEstat) and plain text (CIDR) lists
- **Auto-Collapse**: Automatically merges adjacent subnets to optimize route table size
- **Atomic Updates**: Safe file writes with smoke testing before reloading BIRD
- **Anti-loop (own-infra)**: Your own networks are subtracted from the feed before write (with supernet hole-punching) and rejected in the BIRD export filters; the script is fail-closed without an inventory
- **Strict IPv4 parsing**: Rejects malformed IPv4/CIDR inputs instead of accepting legacy shorthand forms
- **All-or-fallback service groups**: Multi-AS service groups such as Netflix and YouTube fall back to previous routes if any required AS source fails

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
- `conf/custom.lst` — commented template for local custom IPv4 prefixes.
- `conf/own-infra.lst.example` — template for the inventory of own networks that must **never** be advertised (the real `/etc/bird/own-infra.lst` is not tracked; see [Own-infrastructure exclusion](#own-infrastructure-exclusion-anti-loop)).
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
   # Install BIRD config (common, from git)
   install -m644 conf/bird.conf /etc/bird/bird.conf
   install -m644 conf/custom.lst /etc/bird/custom.lst

   # own-infra.lst — your inventory of own networks. Created ONCE from the
   # template and NOT overwritten on updates (idempotent guard). The real file
   # is not stored in git. After creating it, add your own networks.
   # The updater generates /etc/bird/own-infra.conf (define OWN_INFRA) from it,
   # which bird.conf includes — so bird.conf carries no local data and is safe
   # to reinstall from git on every update.
   [ -f /etc/bird/own-infra.lst ] || install -m640 conf/own-infra.lst.example /etc/bird/own-infra.lst

   # Systemd service and timer
   install -m644 systemd/bird2-bgp-prefix-updater.service /etc/systemd/system/
   install -m644 systemd/bird2-bgp-prefix-updater.timer /etc/systemd/system/
   ```

2. **Create local settings (not in git):**
   ```bash
   # Create local-settings.conf with your parameters
   cat > /etc/bird/local-settings.conf <<'EOF'
   log syslog all;
   router id 10.0.0.1;           # Your router ID
   define MY_AS = 65000;         # Your AS number
   EOF

   # Create peers directory
   mkdir -p /etc/bird/peers.d
   ```

3. **Prepare working directories:**
   ```bash
   mkdir -p /var/lib/bird /var/lib/bird/prefix-cache
   touch /etc/bird/prefixes.bird
   chown bird:bird /etc/bird/prefixes.bird # For Debian/Ubuntu
   ```

4. **Add BGP peers** (examples in `/etc/bird/peers.d/`):
   ```bash
   cat > /etc/bird/peers.d/my_peer.conf <<'EOF'
   protocol bgp my_peer from t_client {
       neighbor 192.0.2.2 as 65002;
       ipv4 { export filter export_only_ru; };
   }
   EOF
   ```

5. **Run initial update and start services:**
   ```bash
   # Script automatically detects MY_AS from local-settings.conf.
   # IMPORTANT: run the updater BEFORE starting bird — it generates
   # /etc/bird/own-infra.conf, without which the include in bird.conf fails.
   python3 /opt/bird2-bgp-prefix-updater/src/prefix_updater.py

   systemctl daemon-reload
   systemctl enable --now bird
   systemctl enable --now bird2-bgp-prefix-updater.timer
   ```

### File structure `/etc/bird/`
```
/etc/bird/
  bird.conf                 ← from git (common config, NO local data)
  local-settings.conf       ← your settings (router id, MY_AS, logging)
  peers.d/*.conf            ← your BGP peers (not overwritten)
  prefixes.bird             ← auto-generated by script
  own-infra.conf            ← auto-generated by script (define OWN_INFRA from own-infra.lst)
  custom.lst                ← your custom IPs (starts from the commented template)
  own-infra.lst             ← your own networks (from own-infra.lst.example, NOT in git)
```

When you `git pull`, the repository copy changes only under `/opt/bird2-bgp-prefix-updater`.
Your `/etc/bird/local-settings.conf`, `/etc/bird/own-infra.lst` and `/etc/bird/peers.d/*.conf` files are not tracked by this repository and are not overwritten by `git pull`.
`bird.conf` no longer holds local data (`OWN_INFRA` is moved to the generated `own-infra.conf`), so it is **safe to reinstall from git** on every update.

## BIRD configuration
The generated include file is `/etc/bird/prefixes.bird`. Routes are loaded into the `t_bgp_prefixes` table.

Runtime settings are controlled by local files and environment variables:

| Setting | Default | Purpose |
| :--- | :--- | :--- |
| `MY_AS` in `/etc/bird/local-settings.conf` | `64888` fallback | BGP AS used in generated communities |
| `LOCAL_AS` env var | unset | Overrides `MY_AS` auto-detection |
| `OUTPUT_BIRD` | `/etc/bird/prefixes.bird` | Generated BIRD static routes |
| `OUTPUT_TXT` | `/var/lib/bird/prefixes.txt` | Generated plain CIDR list |
| `BIRD_CONF` | `/etc/bird/bird.conf` | Config used for smoke testing and AS auto-detection |
| `CACHE_DIR` | `/var/lib/bird/prefix-cache` | Download cache directory |
| `CACHE_TTL` | `21600` | Fresh cache lifetime in seconds |
| `STALE_CACHE_MAX_AGE` | `604800` | Maximum stale-cache age used after download failures |

## BGP Communities

Routes are tagged with communities in the format `LOCAL_AS:ID`. IDs are organized into semantic groups by hundreds:

| Range | Purpose |
| :--- | :--- |
| **100..199** | Russian resources — usually routed via the local Russian channel |
| **200..299** | RKN-blocked subnets — routed around the blocking |
| **300..399** | Foreign services — also usually routed around the blocking |

### Russian resources (100..199)
| ID | Name | Description |
| :--- | :--- | :--- |
| **100** | **RU Combined** | All IPv4 networks of Russia (RIPEstat) |
| **110** | **Gov Networks** | Government networks (`govno.lst`) |

### RKN-blocked subnets (200..299)
| ID | Name | Description |
| :--- | :--- | :--- |
| **200** | **Blocked IP** | IP list (`ip.lst`) from Antifilter |
| **210** | **RKN Subnets** | Subnets from Antifilter's official lists |

### Foreign services (300..399)
| ID | Name | Description |
| :--- | :--- | :--- |
| **300** | **Official Services** | **Telegram, Cloudflare, Google** and local `custom.lst` |
| **310** | **Custom User** | Antifilter's `custom.lst` |
| **320** | **Stripe** | Stripe networks (API, Webhooks, etc) |
| **330** | **ByteDance** | AS396986 (ByteDance) prefixes |
| **340** | **Akamai** | AS20940 (Akamai) prefixes |
| **350** | **Roblox** | AS22697 (Roblox) prefixes |
| **360** | **Pinterest** | AS53620 (Pinterest) prefixes |
| **370** | **Fastly** | AS54113 (Fastly CDN) prefixes |
| **380** | **Meta** | AS32934 (Meta/Facebook) prefixes |
| **381** | **Twitter/X** | AS13414 (Twitter/X) prefixes |
| **382** | **Netflix** | AS2906 and AS40027 (Netflix) prefixes; both RIPEstat sources must succeed |
| **383** | **AWS CloudFront** | AWS `CLOUDFRONT` IPv4 prefixes from `ip-ranges.json`; this is a filtered CloudFront list, not all of AWS |
| **384** | **Cloudflare (full)** | All AS13335 announcements (~2400 prefixes) from RIPEstat — a superset of the published CDN ranges in comm `300`; covers non-published blocks like `8.6.112.0/24` that front chatgpt.com |
| **386** | **YouTube** | AS36040 and AS43515 (YouTube) prefixes; both RIPEstat sources must succeed |
| **387** | **Anthropic** | AS399358 prefixes (Anthropic — Claude, console/api.anthropic.com) |
| **388** | **Threema** | Static PI block `203.56.112.0/22` (netname CH-THREEMA); Threema has no own ASN (announced via AS29691/AS15576), so a per-ASN source is not used |

> Groups are split so that simple community ranges can route different categories to different peers. For example, `gov_networks` (110) is a Russian government resource, so it logically belongs in the same group as RU Combined (100), not bundled with foreign blocked services.

### Source notes
- `ru_combined` uses RIPEstat `country-resource-list`, which returns country-associated ASNs, IPv4 ranges/prefixes, and IPv6 prefixes: <https://stat-ui.stat.ripe.net/docs/data-api/api-endpoints/country-resource-list>
- AS-based service sources use RIPEstat `announced-prefixes`, which returns announced prefixes for a requested ASN: <https://stat-ui.stat.ripe.net/docs/data-api/api-endpoints/announced-prefixes>
- `aws_networks` uses AWS `ip-ranges.json`, reads only `prefixes[].ip_prefix`, ignores `ipv6_prefixes`, and filters to the `CLOUDFRONT` service by default: <https://ip-ranges.amazonaws.com/ip-ranges.json>
- `rkn_subnets` uses two mirror URLs and keeps partial success. Netflix and YouTube use additive AS sources and require every URL to succeed before replacing that community.
- `official_services` combines Telegram, Cloudflare, Google, and the local `/etc/bird/custom.lst` file into community `300`; Antifilter's remote `custom.lst` remains separate as community `310`.

### Changing the AWS filter
To add another AWS service, edit `aws_services` on the `aws_networks` source in `src/prefix_updater.py`, for example:
```python
"aws_services": ["CLOUDFRONT", "GLOBALACCELERATOR"],
```
Service names are matched case-insensitively, but keeping the same spelling as AWS `ip-ranges.json` is clearer.
Do not clear the filter without separate validation: the full AWS list is much broader than CloudFront and can materially change routing.

## Own-infrastructure exclusion (anti-loop)

The feed source must **never advertise its own networks**. If a prefix covering your egress/next-hop public IP enters the feed, consumers get a **routing loop**: the route's next-hop falls inside the route itself. Such blocks can legitimately appear in upstream lists (e.g. the RIPEstat RU list, RKN), so fixing one source is pointless — protection is applied **at the set level** (source-agnostic).

Three layers:

1. **Generator subtraction (primary, L1).** `src/prefix_updater.py` subtracts own-infra from the set **before** writing the feed, so it physically contains none of its own networks at any prefix length. If a source returns a supernet (e.g. a `/16` containing your `/24`), it is not dropped wholesale but hole-punched (`ipaddress.address_exclude`): everything **except** the own block is advertised. A **fail-closed** self-check then aborts the run (keeping the old file) if any own-infra prefix survived.
2. **BIRD export filter (safety net, L2).** `define OWN_INFRA = [ ... ];` is **generated** by the updater from `own-infra.lst` into `/etc/bird/own-infra.conf` (single source of truth — L1 and L2 never drift, and the git-tracked `bird.conf` holds none of your networks), and `bird.conf` pulls it in via `include`. `if net ~ OWN_INFRA then reject;` is the **first statement of every named filter** (`export_only_ru`, `export_blocked_lists`, …) and the `t_client` template — because peers use named filters that override the template's anonymous filter. The `+` suffix matches the prefix and all **more-specifics** (closes the "/24 vs /23" gap). Note: `+` does **not** match a less-specific supernet — that is handled only by L1.
3. **Downstream inbound filter (L3).** The receiving router (pfSense/FRR) filters own-infra inbound as a last resort.

### Source of truth — `own-infra.lst`

The list is maintained **manually** in `/etc/bird/own-infra.lst` (override the path with `OWN_INFRA_FILE`). It is your inventory of egress/tunnel-endpoint public IPs — add a node's network when you provision it. Only the `conf/own-infra.lst.example` template is tracked in git; the real `/etc/bird/own-infra.lst` is **not stored in the repo and is not overwritten** by `git pull` (and the path `conf/own-infra.lst` is in `.gitignore` as a safety net against accidentally committing real data).

File format:
- one IPv4 address (becomes `/32`) or CIDR per line;
- `#` starts a comment, full-line or **inline**: `198.51.100.0/24  # node A egress`;
- **IPv4/CIDR only — hostnames are not supported** (DNS is non-deterministic and a network dependency; a failed/poisoned lookup = own network not excluded = loop);
- a node with **many addresses** — list one covering CIDR or each `/32` explicitly; do not rely on DNS;
- unparseable lines are skipped with a WARNING (check the log) and are therefore **not protected** — keep the list clean.

**Fail-closed:** there are no built-in defaults, so the file is mandatory. If `/etc/bird/own-infra.lst` is missing or contains no valid prefixes, the script **refuses to publish a feed** (`exit 1`, the old file is kept). The script does **not** create the file itself.

What to add, what not:
- **Add:** next-hop/egress and your tunnel-endpoint public IPs; if needed, the underlay/transit prefix downstream uses to reach the next-hop.
- **Do not add:** downstream BGP routers — they are feed consumers protected by their own connected routes and inbound filter. Exception: such a router that has interfaces in address space that could appear in a source list.

> Note: the pipeline is IPv4-only (the feed is v4-only). IPv6 endpoints are out of scope for this mechanism.

## Filtering Examples (BIRD2)

Thanks to the by-hundreds grouping, filters read like natural language:

### Russian resources only (RU Combined + Gov Networks)
For peers that should carry only Russian networks:
```bird
filter export_only_ru {
    if (bgp_community ~ [(MY_AS, 100..199)]) then accept;
    reject;
}
```

### Blocked subnets + foreign services (no Russian prefixes)
For peers that need to bypass RKN blocking but should not get RU prefixes:
```bird
filter export_blocked_lists {
    if (bgp_community ~ [(MY_AS, 200..399)]) then accept;
    reject;
}
```

### RKN-blocked subnets only (without foreign services)
```bird
filter export_blocked_only {
    if (bgp_community ~ [(MY_AS, 200..299)]) then accept;
    reject;
}
```

### Foreign services only (without RKN blocked lists)
```bird
filter export_services_only {
    if (bgp_community ~ [(MY_AS, 300..399)]) then accept;
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

### MikroTik RouterOS 7

Full example of a client that receives prefixes from BIRD and routes traffic through a chosen gateway. Filtering by traffic type (RU / blocked / foreign services) is done on the BIRD side via `export filter` in `peers.d/`.

**Placeholders (replace with your values):**

| Placeholder | Meaning |
|---|---|
| `BIRD_IP` | BIRD server address (public or private — does not matter) |
| `MY_ROUTER_ID` | Router-ID of MikroTik, any unique IPv4 |
| `GW_ADDR` | Gateway for traffic forwarding (VPN tunnel IP, ZeroTier, physical interface, etc.) |
| `LOCAL_AS` | Client AS (see `peers.d/*.conf` on the server) |
| `REMOTE_AS` | BIRD server AS (`MY_AS` from `local-settings.conf`) |

> `BIRD_IP` and `GW_ADDR` are **different networks**. The BGP session may go through one channel (e.g., internet), while traffic for received routes flows through another (VPN tunnel).

> **Dynamic client:** if MikroTik has no static address — use `neighbor range X.X.X.X/Y as ... ; dynamic name "...";` on the BIRD side (see `peers.d/LAN.conf`).

#### 1. BGP connection

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

| Parameter | Purpose |
|---|---|
| `multihop=yes` | BIRD is configured with `multihop` — there may be multiple hops between them |
| `connect=yes listen=no` | MikroTik initiates the connection, BIRD is passive (`passive on`) |
| `output.filter-chain=discard` | Do not advertise routes back to BIRD |
| `input.ignore-as-path-len=yes` | Bypass AS-path length check for multihop |

#### 2. Route filters

```shell
/routing filter rule
# discard chain — rejects everything (used in output.filter-chain above)
add chain=discard rule="reject;"

# bgp-in chain — processes incoming routes from BIRD
# Safety: do not hijack the BGP peer itself
add chain=bgp-in rule="if (dst in BIRD_IP/32) { reject; }"

# All received routes — through the chosen gateway
add chain=bgp-in rule="set gw GW_ADDR; accept;"

# Default deny
add chain=bgp-in rule="reject;"
```

`GW_ADDR` can be an IP address or an interface name (`wg-tunnel`, `gre-tunnel1`, `zerotier1`).

#### 3. Route to the gateway (optional)

If `GW_ADDR` is reachable only via some interface/tunnel and is not auto-resolved — add a static route:

```shell
/ip route
add dst-address=GW_ADDR/32 gateway=<your-tunnel-iface-or-ip> check-gateway=ping
```

#### 4. Verification

```shell
# BGP session state (must be established)
/routing bgp session print

# Number of accepted routes
/ip route print count-only where bgp

# Specific route
/ip route print where dst-address="149.154.160.0/20"
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

## Diagnostics and Debugging
### Finding the source of a prefix
If you find that an IP is blocked or allowed incorrectly, you can quickly find which list it came from:
```bash
python3 /opt/bird2-bgp-prefix-updater/src/prefix_updater.py --check 194.67.72.31
python3 /opt/bird2-bgp-prefix-updater/src/prefix_updater.py --check 3.10.17.128/25
```
The script will check all sources and output the source name, URL, and assigned Community ID.

### Caching
The script caches downloaded lists in `/var/lib/bird/prefix-cache` for **6 hours** (`CACHE_TTL`). When a source fails, stale cache is reused for up to 7 days (`STALE_CACHE_MAX_AGE`). Both values can be overridden via environment variables.
- To force a cache refresh, use the `--force-refresh` flag:
  ```bash
  python3 /opt/bird2-bgp-prefix-updater/src/prefix_updater.py --force-refresh
  ```

### General commands
- **BGP Status**: `birdc show protocols`
- **View all routes in table**: `birdc "show route table t_bgp_prefixes"`
- **Detailed info for a specific IP**: `birdc "show route for 77.88.44.242 table t_bgp_prefixes all"`
- **Force manual update**: `systemctl start bird2-bgp-prefix-updater.service`
- **Update logs**: `journalctl -u bird2-bgp-prefix-updater.service -f`

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
- Export limit `500000` is set in the BIRD client template to protect clients from route table overflow (`action disable` drops the session if exceeded, so it is kept well above the live feed size — ~103k with the full Cloudflare source).

[itforprof.com](https://itforprof.com) by Konstantin Tyutyunnik
