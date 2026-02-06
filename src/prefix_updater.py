#!/usr/bin/env python3
# itforprof.com by Konstantin Tyutyunnik

import json
import urllib.request
import urllib.error
import socket
import struct
import os
import sys
import hashlib
import math
import time
import argparse
import re
from typing import List, Tuple, Dict, Set, Optional

# Configuration
OUTPUT_TXT = os.environ.get('OUTPUT_TXT', "/var/lib/bird/prefixes.txt")
OUTPUT_BIRD = os.environ.get('OUTPUT_BIRD', "/etc/bird/prefixes.bird")
BIRD_CONF = os.environ.get('BIRD_CONF', "/etc/bird/bird.conf")


def _detect_local_as() -> int:
    """Auto-detect MY_AS from BIRD config (local-settings.conf included via bird.conf)."""
    env_as = os.environ.get('LOCAL_AS')
    if env_as:
        return int(env_as)
    # Search BIRD config directory for 'define MY_AS = <number>'
    bird_dir = os.path.dirname(BIRD_CONF)
    for filename in [os.path.join(bird_dir, 'local-settings.conf'), BIRD_CONF]:
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    for line in f:
                        match = re.match(r'\s*define\s+MY_AS\s*=\s*(\d+)\s*;', line)
                        if match:
                            return int(match.group(1))
            except Exception:
                continue
    print("WARNING: Could not detect MY_AS from BIRD config, using default 64888")
    return 64888


LOCAL_AS = _detect_local_as()
CACHE_DIR = os.environ.get('CACHE_DIR', "/var/lib/bird/prefix-cache")
CACHE_TTL = int(os.environ.get('CACHE_TTL', '21600'))  # 6 hours
STALE_CACHE_MAX_AGE = int(os.environ.get('STALE_CACHE_MAX_AGE', '604800'))  # 7 days
USER_AGENT = 'Mozilla/5.0 (compatible; BIRD2-BGP-Prefix-Updater/2.9; +itforprof.com)'
MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds

# Data Sources (Verified working URLs)
SOURCES = [
    {
        "name": "ru_combined",
        "url": "https://stat.ripe.net/data/country-resource-list/data.json?resource=ru",
        "community_suffix": 100,
        "format": "json"
    },
    # {
    #     "name": "blocked_smart",
    #     "urls": [
    #         "https://antifilter.network/download/ipsmart.lst"
    #     ],
    #     "community_suffix": 101,
    #     "format": "text"
    # },
    # {
    #     "name": "blocked_sum",
    #     "urls": [
    #         "https://antifilter.network/download/ipsum.lst"
    #     ],
    #     "community_suffix": 105,
    #     "format": "text"
    # },
    {
        "name": "blocked_ip",
        "urls": [
            "https://antifilter.network/download/ip.lst"
        ],
        "community_suffix": 106,
        "format": "text"
    },
    {
        "name": "rkn_subnets",
        "urls": [
            "https://antifilter.network/download/subnet.lst",
            "https://antifilter.download/list/subnet.lst"
        ],
        "community_suffix": 102,
        "format": "text"
    },
    {
        "name": "gov_networks",
        "url": "https://antifilter.network/download/govno.lst",
        "community_suffix": 103,
        "format": "text"
    },
    {
        "name": "official_services",
        "urls": [
            "https://core.telegram.org/resources/cidr.txt",
            "https://www.cloudflare.com/ips-v4",
            "https://www.gstatic.com/ipranges/goog.txt",
            "/etc/bird/custom.lst"  # Local file
        ],
        "community_suffix": 104,
        "format": "text"
    },
    {
        "name": "custom_user",
        "url": "https://antifilter.network/downloads/custom.lst",
        "community_suffix": 104,
        "format": "text"
    },
    {
        "name": "stripe_networks",
        "urls": [
            "https://stripe.com/files/ips/ips_api.txt",
            "https://stripe.com/files/ips/ips_armada_gator.txt",
            "https://stripe.com/files/ips/ips_webhooks.txt"
        ],
        "community_suffix": 107,
        "format": "text"
    },
    {
        "name": "bytedance_as396986",
        "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS396986",
        "community_suffix": 108,
        "format": "json"
    },
    {
        "name": "akamai_as20940",
        "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS20940",
        "community_suffix": 109,
        "format": "json"
    },
    {
        "name": "roblox_as22697",
        "url": "https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS22697",
        "community_suffix": 110,
        "format": "json"
    }
]


def ip_to_int(ip: str) -> int:
    return struct.unpack("!I", socket.inet_aton(ip))[0]


def int_to_ip(n: int) -> str:
    return socket.inet_ntoa(struct.pack("!I", n))


def cidr_to_range(cidr: str) -> Tuple[int, int]:
    if '/' not in cidr:
        cidr = f"{cidr}/32"
    ip, prefix = cidr.split('/')
    prefix = int(prefix)
    start = ip_to_int(ip)
    mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
    start &= mask
    end = start + (1 << (32 - prefix)) - 1
    return start, end


def range_to_cidrs(start: int, end: int) -> List[str]:
    cidrs: List[str] = []
    while start <= end:
        max_size = 32
        if start != 0:
            trailing_zeros = 0
            temp_start = start
            while temp_start % 2 == 0:
                trailing_zeros += 1
                temp_start //= 2
            max_size = trailing_zeros
        range_len = end - start + 1
        max_from_len = int(math.log2(range_len)) if range_len > 0 else 0
        prefix_len = 32 - min(max_size, max_from_len)
        cidrs.append(f"{int_to_ip(start)}/{prefix_len}")
        start += (1 << (32 - prefix_len))
    return cidrs


def collapse_networks(networks: List[str]) -> List[str]:
    if not networks:
        return []
    ranges: List[Tuple[int, int]] = []
    for n in networks:
        try:
            ranges.append(cidr_to_range(n))
        except Exception:
            continue
    if not ranges:
        return []
    ranges.sort()
    collapsed_ranges: List[Tuple[int, int]] = []
    curr_start, curr_end = ranges[0]
    for next_start, next_end in ranges[1:]:
        if next_start <= curr_end + 1:
            curr_end = max(curr_end, next_end)
        else:
            collapsed_ranges.append((curr_start, curr_end))
            curr_start, curr_end = next_start, next_end
    collapsed_ranges.append((curr_start, curr_end))
    result: List[str] = []
    for s, e in collapsed_ranges:
        result.extend(range_to_cidrs(s, e))
    return result


def validate_cidr(cidr: str) -> bool:
    try:
        if '/' not in cidr:
            cidr = f"{cidr}/32"
        ip, pfx = cidr.split('/')
        pfx = int(pfx)
        if not (0 <= pfx <= 32):
            return False
        socket.inet_aton(ip)
        return True
    except Exception:
        return False


def atomic_write(filename: str, content: str) -> None:
    tmp = filename + ".tmp"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    if os.name == 'nt' and os.path.exists(filename):
        os.remove(filename)
    os.rename(tmp, filename)


def parse_old_prefixes(filepath: str) -> Dict[str, Set[int]]:
    """Parse existing prefixes.bird file into {CIDR: set of community suffixes}."""
    result: Dict[str, Set[int]] = {}
    if not os.path.exists(filepath):
        return result
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line.startswith('route '):
                continue
            parts = line.split()
            cidr = parts[1]
            comms: Set[int] = set()
            for match in re.finditer(r'\(\d+,\s*(\d+)\)', line):
                comms.add(int(match.group(1)))
            if cidr and comms:
                result[cidr] = comms
    return result


def _parse_cached_data(cache_path: str, source: Dict) -> Optional[List[str]]:
    """Parse a cached file for a given source. Returns list of prefixes or None on error."""
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            raw_data = f.read()
        if source['format'] == 'json':
            data = json.loads(raw_data)
            d = data.get('data', {})
            res = d.get('resources', {}).get('ipv4', [])
            if res:
                return res
            prefixes = d.get('prefixes', [])
            if prefixes:
                return [p['prefix'] for p in prefixes if 'prefix' in p]
            return []
        else:
            return [line.strip() for line in raw_data.splitlines()
                    if line.strip() and not line.startswith('#')]
    except Exception as e:
        print(f"Cache parse error for {source['name']}: {e}")
        return None


def download_resource(source: Dict, force_refresh: bool = False) -> Optional[List[str]]:
    url = source['url']
    
    # Handle local files
    if not url.startswith('http'):
        if os.path.exists(url):
            try:
                with open(url, 'r', encoding='utf-8') as f:
                    return [line.strip() for line in f if line.strip() and not line.startswith('#')]
            except Exception as e:
                print(f"Error reading local file {url}: {e}")
                return []
        else:
            print(f"Warning: Local file {url} not found.")
            return []

    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    cache_path = os.path.join(CACHE_DIR, f"{source['name']}_{url_hash}.cache")

    if not force_refresh and os.path.exists(cache_path):
        mtime = os.path.getmtime(cache_path)
        if time.time() - mtime < CACHE_TTL:
            result = _parse_cached_data(cache_path, source)
            if result is not None:
                print(f"Using cached data for {source['name']} ({url})")
                return result
            else:
                print(f"Cache read error for {source['name']}: re-downloading...")

    print(f"Downloading {source['name']} from {url}...")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as response:
                raw_data = response.read().decode('utf-8')
                
                # Save to cache
                try:
                    os.makedirs(CACHE_DIR, exist_ok=True)
                    with open(cache_path, 'w', encoding='utf-8') as f:
                        f.write(raw_data)
                except Exception as e:
                    print(f"Warning: Failed to write cache: {e}")

                if source['format'] == 'json':
                    data = json.loads(raw_data)
                    d = data.get('data', {})
                    # Path 1: country-resource-list
                    res = d.get('resources', {}).get('ipv4', [])
                    if res: return res
                    # Path 2: announced-prefixes
                    prefixes = d.get('prefixes', [])
                    if prefixes:
                        return [p['prefix'] for p in prefixes if 'prefix' in p]
                    return []
                else:
                    return [line.strip() for line in raw_data.splitlines() if line.strip() and not line.startswith('#')]
        except Exception as e:
            if attempt == MAX_RETRIES:
                print(f"Error: Failed to download {source['name']} after {MAX_RETRIES} attempts: {e}")
                # Fallback: try stale cache within STALE_CACHE_MAX_AGE
                if os.path.exists(cache_path):
                    cache_age = time.time() - os.path.getmtime(cache_path)
                    if cache_age <= STALE_CACHE_MAX_AGE:
                        stale_data = _parse_cached_data(cache_path, source)
                        if stale_data:
                            print(f"WARNING: Using stale cache for {source['name']} (age: {cache_age/3600:.1f}h)")
                            return stale_data
                    else:
                        print(f"WARNING: Stale cache for {source['name']} too old ({cache_age/86400:.1f} days), discarding")
                return None
            print(f"Attempt {attempt} failed for {source['name']}: {e}. Retrying in {RETRY_DELAY * (2 ** (attempt - 1))}s...")
            time.sleep(RETRY_DELAY * (2 ** (attempt - 1)))
    return None


def check_address_in_sources(target: str, force_refresh: bool = False) -> None:
    """Diagnostic tool to find which source contains a specific IP or CIDR"""
    print(f"\n--- Diagnostic Search for {target} ---")
    try:
        t_start, t_end = cidr_to_range(target)
    except Exception as e:
        print(f"Error: Invalid search target '{target}': {e}")
        return

    found_any = False
    for src in SOURCES:
        urls = src.get('urls', [src.get('url')])
        for url in urls:
            if not url:
                continue
            temp_src = src.copy()
            temp_src['url'] = url
            prefixes = download_resource(temp_src, force_refresh=force_refresh)
            if prefixes is None:
                continue

            for item in prefixes:
                item = item.strip()
                if not item:
                    continue
                try:
                    if '-' in item:
                        p = [x.strip() for x in item.split('-')]
                        p_start, p_end = ip_to_int(p[0]), ip_to_int(p[1])
                    else:
                        p_start, p_end = cidr_to_range(item if '/' in item else f"{item}/32")
                    
                    # Check for overlap
                    if max(t_start, p_start) <= min(t_end, p_end):
                        print(f"  [!] MATCH FOUND in source: {src['name']}")
                        print(f"      Matched prefix: {item}")
                        print(f"      Source URL: {url}")
                        print(f"      Assigned Community ID: {src['community_suffix']}")
                        print("-" * 40)
                        found_any = True
                except:
                    continue
    
    if not found_any:
        print(f"Result: {target} was not found in any source.")
    print("-" * 40)

    # BIRD Internal Table Check
    print(f"\n--- BIRD Internal Table Check ---")
    bird_cmd = f'birdc "show route for {target} table t_bgp_prefixes all"'
    print(f"Running: {bird_cmd}\n")
    
    # Run birdc and let it output directly to stdout
    res = os.system(bird_cmd)
    if res != 0:
        print("\n[!] Note: birdc command failed. Possible reasons:")
        print("    - BIRD is not running")
        print("    - Table 't_bgp_prefixes' does not exist")
        print("    - Insufficient permissions to run birdc")
    
    print("-" * 40 + "\n")


def smoke_test_bird(temp_bird_file: str) -> bool:
    if not os.path.exists(BIRD_CONF):
        print(f"Warning: {BIRD_CONF} not found, skipping smoke test.")
        return True

    check_conf = BIRD_CONF + ".check"
    try:
        with open(BIRD_CONF, 'r', encoding='utf-8') as f:
            conf_data = f.read()

        new_include = f'include "{temp_bird_file}";'
        old_include_pattern = f'include "{OUTPUT_BIRD}";'

        if old_include_pattern not in conf_data:
            print(f"Warning: Could not find '{old_include_pattern}' in {BIRD_CONF}. Smoke test might be inaccurate.")

        check_conf_data = conf_data.replace(old_include_pattern, new_include)

        with open(check_conf, 'w', encoding='utf-8') as f:
            f.write(check_conf_data)

        # bird -p -c returns 0 on success
        res = os.system(f"bird -p -c {check_conf}")
        return res == 0
    except Exception as e:
        print(f"Smoke test error: {e}")
        return False
    finally:
        if os.path.exists(check_conf):
            try:
                os.remove(check_conf)
            except Exception:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description='BIRD2 BGP Prefix Updater - Automates downloading and aggregating BGP prefixes from multiple sources.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                        # Run update (standard mode)
  %(prog)s --check 1.1.1.1        # Check which source contains this IP
  %(prog)s --check 194.67.72.0/24 # Check which source contains this subnet
  %(prog)s --force-refresh        # Ignore cache and download all sources fresh
        """
    )
    parser.add_argument('--check', type=str, help='Check which source contains a specific IP or CIDR (diagnostic mode)')
    parser.add_argument('--force-refresh', action='store_true', help='Ignore local cache and download everything from the Internet')
    args = parser.parse_args()

    if args.check:
        check_address_in_sources(args.check, force_refresh=args.force_refresh)
        return

    start_time = time.time()
    print(f"=== BIRD2 BGP Prefix Updater ===")
    print(f"AS: {LOCAL_AS} | Cache TTL: {CACHE_TTL//3600}h | Stale limit: {STALE_CACHE_MAX_AGE//86400}d")
    print()

    all_routes: Dict[str, Set[int]] = {}  # CIDR -> set of community suffixes
    old_routes = parse_old_prefixes(OUTPUT_BIRD)
    failed_communities: Set[int] = set()
    source_stats: List[Tuple[str, int, int, str]] = []  # (name, community, count, status)

    for src in SOURCES:
        urls = src.get('urls', [src.get('url')])
        all_src_prefixes: List[str] = []
        any_success = False
        failed_urls: List[str] = []

        for url in urls:
            if not url:
                continue
            # Create a shallow copy to safely update the URL for the download function
            temp_src = src.copy()
            temp_src['url'] = url
            result = download_resource(temp_src, force_refresh=args.force_refresh)
            if result is None:
                failed_urls.append(url)
            else:
                all_src_prefixes.extend(result)
                any_success = True

        if not any_success:
            failed_communities.add(src['community_suffix'])
            # Count old routes for this community
            old_count = sum(1 for comms in old_routes.values() if src['community_suffix'] in comms)
            source_stats.append((src['name'], src['community_suffix'], old_count, 'FALLBACK'))
            for url in failed_urls:
                print(f"  ERROR: {url}")
            continue

        if failed_urls:
            for url in failed_urls:
                print(f"  WARNING: Failed URL (other URLs OK): {url}")

        processed: List[str] = []
        for item in all_src_prefixes:
            item = item.strip()
            if not item:
                continue
            if '-' in item:
                try:
                    p = [x.strip() for x in item.split('-')]
                    processed.extend(range_to_cidrs(ip_to_int(p[0]), ip_to_int(p[1])))
                except Exception:
                    continue
            else:
                processed.append(item if '/' in item else f"{item}/32")

        valid = [p for p in processed if validate_cidr(p)]
        collapsed = collapse_networks(valid)

        source_stats.append((src['name'], src['community_suffix'], len(collapsed), 'OK'))

        for p in collapsed:
            all_routes.setdefault(p, set()).add(src['community_suffix'])

    # Restore old routes for failed communities
    if failed_communities:
        restored = 0
        for cidr, comms in old_routes.items():
            for comm in comms:
                if comm in failed_communities:
                    all_routes.setdefault(cidr, set()).add(comm)
                    restored += 1
        print(f"\n  Restored {restored} old routes for communities: {sorted(failed_communities)}")

    # Print summary table
    print(f"\n{'Source':<25} {'Comm':>4} {'Prefixes':>10} {'Status':<10}")
    print("-" * 55)
    for name, comm, count, status in source_stats:
        status_str = status
        if status == 'FALLBACK':
            status_str = 'FALLBACK!'
        print(f"  {name:<23} {comm:>4} {count:>10} {status_str:<10}")
    print("-" * 55)

    if not all_routes:
        print("\nERROR: No prefixes collected from any source.")
        sys.exit(1)

    # Per-community totals
    comm_totals: Dict[int, int] = {}
    for comms in all_routes.values():
        for c in comms:
            comm_totals[c] = comm_totals.get(c, 0) + 1
    print(f"  {'TOTAL':<23} {'':>4} {len(all_routes):>10}")
    print(f"\nPer-community breakdown:")
    for comm in sorted(comm_totals.keys()):
        print(f"  Community {comm:>3}: {comm_totals[comm]:>10} routes")

    sorted_cidrs = sorted(all_routes.keys(), key=lambda x: (ip_to_int(x.split('/')[0]), int(x.split('/')[1])))

    txt_content = "\n".join(sorted_cidrs)
    bird_lines = []
    for cidr in sorted_cidrs:
        comms = sorted(list(all_routes[cidr]))
        # Correct format: bgp_community.add((ASN, VALUE));
        # If multiple: { bgp_community.add((ASN, V1)); bgp_community.add((ASN, V2)); }
        adds = [f"bgp_community.add(({LOCAL_AS}, {suffix}));" for suffix in comms]
        bird_lines.append(f"route {cidr} blackhole {{ {' '.join(adds)} }};")

    bird_content = "\n".join(bird_lines)

    # Self-check
    if "bgp_community.add([(" in bird_content:
        print("\nERROR: Invalid community format detected (found 'bgp_community.add([(').")
        invalid = [l for l in bird_lines if "bgp_community.add([(" in l]
        for l in invalid[:5]:
            print(f"  Invalid line: {l}")
        sys.exit(1)

    new_hash = hashlib.sha256(bird_content.encode()).hexdigest()
    old_hash = ""
    if os.path.exists(OUTPUT_BIRD):
        with open(OUTPUT_BIRD, 'r', encoding='utf-8') as f:
            old_hash = hashlib.sha256(f.read().encode()).hexdigest()

    elapsed = time.time() - start_time

    if new_hash == old_hash:
        failed = sum(1 for _, _, _, s in source_stats if s == 'FALLBACK')
        ok = sum(1 for _, _, _, s in source_stats if s == 'OK')
        print(f"\nResult: No changes | {ok} OK, {failed} fallback | "
              f"Total: {len(all_routes)} routes | {elapsed:.1f}s")
        return

    # Atomic write for TXT
    atomic_write(OUTPUT_TXT, txt_content)

    # Atomic write with smoke test for BIRD
    temp_bird = OUTPUT_BIRD + ".tmp"
    os.makedirs(os.path.dirname(OUTPUT_BIRD), exist_ok=True)
    with open(temp_bird, 'w', encoding='utf-8', newline='\n') as f:
        f.write(bird_content)
        f.flush()
        os.fsync(f.fileno())

    print("\nRunning smoke test...")
    if smoke_test_bird(temp_bird):
        if os.name == 'nt' and os.path.exists(OUTPUT_BIRD):
            os.remove(OUTPUT_BIRD)
        os.rename(temp_bird, OUTPUT_BIRD)

        # Reload BIRD
        if os.system("birdc configure") != 0:
            print("WARNING: birdc configure failed. Is BIRD running?")

        elapsed = time.time() - start_time
        failed = sum(1 for _, _, _, s in source_stats if s == 'FALLBACK')
        ok = sum(1 for _, _, _, s in source_stats if s == 'OK')
        print(f"\nResult: Updated | {ok} OK, {failed} fallback | "
              f"Total: {len(all_routes)} routes | Hash: {new_hash[:8]} | {elapsed:.1f}s")
    else:
        print("\nERROR: Smoke test failed. New configuration is invalid. Keeping old file.")
        if os.path.exists(temp_bird):
            os.remove(temp_bird)
        sys.exit(1)


if __name__ == "__main__":
    main()
