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
from typing import List, Tuple, Dict, Set

# Configuration
LOCAL_AS = int(os.environ.get('LOCAL_AS', '64888'))
OUTPUT_TXT = os.environ.get('OUTPUT_TXT', "/var/lib/bird/prefixes.txt")
OUTPUT_BIRD = os.environ.get('OUTPUT_BIRD', "/etc/bird/prefixes.bird")
USER_AGENT = 'Mozilla/5.0 (compatible; BIRD2-BGP-Prefix-Updater/2.0; +itforprof.com)'
MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds

# Data Sources (Verified working URLs)
SOURCES = [
    {
        "name": "ru_ripe",
        "url": "https://stat.ripe.net/data/country-resource-list/data.json?resource=ru",
        "community_suffix": 100,
        "format": "json"
    },
    {
        "name": "ipsum_af_network",
        "url": "https://antifilter.network/download/ipsum.lst",
        "community_suffix": 101,
        "format": "text"
    },
    {
        "name": "ipsum_af_download",
        "url": "https://antifilter.download/list/ipsum.lst",
        "community_suffix": 101,
        "format": "text"
    },
    {
        "name": "rkn_subnets_af_network",
        "url": "https://antifilter.network/download/subnet.lst",
        "community_suffix": 102,
        "format": "text"
    },
    {
        "name": "rkn_subnets_af_download",
        "url": "https://antifilter.download/list/subnet.lst",
        "community_suffix": 102,
        "format": "text"
    },
    {
        "name": "custom_af_network",
        "url": "https://antifilter.network/downloads/custom.lst",
        "community_suffix": 104,
        "format": "text"
    },
    {
        "name": "gov_networks",
        "url": "https://antifilter.network/download/govno.lst",
        "community_suffix": 105,
        "format": "text"
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


def download_resource(source: Dict) -> List[str]:
    print(f"Downloading {source['name']} from {source['url']}...")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(source['url'], headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as response:
                raw_data = response.read().decode('utf-8')
                if source['format'] == 'json':
                    data = json.loads(raw_data)
                    return data.get('data', {}).get('resources', {}).get('ipv4', [])
                else:
                    return [line.strip() for line in raw_data.splitlines() if line.strip() and not line.startswith('#')]
        except Exception as e:
            if attempt == MAX_RETRIES:
                print(f"Error: Failed to download {source['name']} after {MAX_RETRIES} attempts: {e}")
                return []
            print(f"Attempt {attempt} failed for {source['name']}: {e}. Retrying...")
            time.sleep(RETRY_DELAY)
    return []


def main() -> None:
    all_routes: Dict[str, Set[int]] = {}  # CIDR -> set of community suffixes

    for src in SOURCES:
        prefixes = download_resource(src)
        processed: List[str] = []
        for item in prefixes:
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

        for p in collapsed:
            if p not in all_routes:
                all_routes[p] = set()
            all_routes[p].add(src['community_suffix'])

    if not all_routes:
        print("Error: No prefixes collected from any source.")
        sys.exit(1)

    sorted_cidrs = sorted(all_routes.keys(), key=lambda x: (ip_to_int(x.split('/')[0]), int(x.split('/')[1])))

    txt_content = "\n".join(sorted_cidrs)
    bird_lines = []
    for cidr in sorted_cidrs:
        comms = sorted(list(all_routes[cidr]))
        comm_str = ", ".join([f"({LOCAL_AS}, {suffix})" for suffix in comms])
        bird_lines.append(f"route {cidr} blackhole {{ bgp_community.add([{comm_str}]); }};")

    bird_content = "\n".join(bird_lines)

    new_hash = hashlib.sha256(bird_content.encode()).hexdigest()
    old_hash = ""
    if os.path.exists(OUTPUT_BIRD):
        with open(OUTPUT_BIRD, 'r', encoding='utf-8') as f:
            old_hash = hashlib.sha256(f.read().encode()).hexdigest()

    if new_hash == old_hash:
        print(f"No changes. Total routes: {len(all_routes)}")
        return

    atomic_write(OUTPUT_TXT, txt_content)
    atomic_write(OUTPUT_BIRD, bird_content)
    print(f"Updated. Total routes: {len(all_routes)}, Hash: {new_hash[:8]}")

    if os.system("birdc configure") != 0:
        print("Warning: birdc configure failed. Is BIRD running?")


if __name__ == "__main__":
    main()
