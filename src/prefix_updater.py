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
from typing import List, Tuple, Dict


# Configuration
URL = os.environ.get('RIPESTAT_URL', 'https://stat.ripe.net/data/country-resource-list/data.json?resource=ru')
OUTPUT_TXT = "/var/lib/bird/prefixes.txt"
OUTPUT_BIRD = "/etc/bird/prefixes.bird"
USER_AGENT = 'Mozilla/5.0 (compatible; BIRD2-BGP-Prefix-Updater/1.0; +itforprof.com)'
MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds


def ip_to_int(ip: str) -> int:
    return struct.unpack("!I", socket.inet_aton(ip))[0]


def int_to_ip(n: int) -> str:
    return socket.inet_ntoa(struct.pack("!I", n))


def cidr_to_range(cidr: str) -> Tuple[int, int]:
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
        max_from_len = int(math.log2(range_len))
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
            return False
        ip, pfx = cidr.split('/')
        pfx = int(pfx)
        if not (8 <= pfx <= 32):
            return False
        socket.inet_aton(ip)
        return True
    except Exception:
        return False


def atomic_write(filename: str, content: str) -> None:
    tmp = filename + ".tmp"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, filename)


def download_data() -> Dict:
    data = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(URL, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
                break
        except (urllib.error.URLError, socket.timeout, json.JSONDecodeError, ConnectionRefusedError) as e:
            if attempt == MAX_RETRIES:
                print(f"Error: All {MAX_RETRIES} attempts failed. Last error: {e}")
                sys.exit(1)
            print(f"Attempt {attempt} failed: {e}. Retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)
    if data is None:
        print("Error: No data retrieved.")
        sys.exit(1)
    return data


def main() -> None:
    print(f"Starting update from {URL}")
    data = download_data()
    try:
        raw_ips = data.get('data', {}).get('resources', {}).get('ipv4', [])
        print(f"Fetched {len(raw_ips)} raw items")

        processed: List[str] = []
        for item in raw_ips:
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
                processed.append(item)

        valid = [ip for ip in processed if validate_cidr(ip)]
        final = collapse_networks(valid)

        if not final:
            print("Error: No prefixes found after validation.")
            sys.exit(1)

        txt_content = "\n".join(final)
        bird_content = "\n".join([f"route {ip} blackhole;" for ip in final])

        new_hash = hashlib.sha256(txt_content.encode()).hexdigest()
        old_hash = ""
        old_prefixes = set()
        if os.path.exists(OUTPUT_TXT):
            with open(OUTPUT_TXT, 'r', encoding='utf-8') as f:
                content = f.read()
                old_hash = hashlib.sha256(content.encode()).hexdigest()
                old_prefixes = set(line.strip() for line in content.splitlines() if line.strip())

        if new_hash == old_hash:
            print(f"No changes. Total: {len(final)}")
            return

        added = len(set(final) - old_prefixes)
        removed = len(old_prefixes - set(final))

        atomic_write(OUTPUT_TXT, txt_content)
        atomic_write(OUTPUT_BIRD, bird_content)
        print(f"Updated. Total: {len(final)} (Added: {added}, Removed: {removed}), Hash: {new_hash[:8]}")

        if os.system("birdc configure") != 0:
            print("Warning: birdc configure failed. Is BIRD running?")

    except Exception as e:
        print(f"Critical Error during processing: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

