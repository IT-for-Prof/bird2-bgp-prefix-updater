# Feed Dedup — Drop Covered More-Specifics Implementation Plan

> **OUTCOME (2026-06-25):** The dry-run against the live feed showed the universal community-superset rule drops **0** routes — `collapse_networks` already removes same-community nesting, so all redundancy is cross-community (e.g. a `200` `/32` under a `300`/`384` `/24`). The shipped implementation therefore added an opt-in `--aggregate-classes LO-HI,...` flag: a more-specific is dropped when its covering supernet shares the same community *class* (a declared accept-range). This is gated by a fail-closed `validate_classes_against_peers()` guard that aborts if any peer filter partially overlaps a class. Verified on ifp-vps02: `--aggregate-classes 100-199,200-399` → 111048 → 77337 (−30.4%), idempotent, all 33711 drops still covered by a kept supernet, BIRD smoke-test PASS. Default (no flag) = unchanged behavior. Tasks below describe the original universal-safe design; the final code generalizes Task 1's function with a `classes` parameter.


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Shrink the generated BGP feed by ~33% (≈36.5k of 111k routes) by dropping more-specific prefixes that are already covered by a less-specific prefix in the same feed, with zero change to blocking behavior **for community-monotone export filters** (see Safety precondition below).

**Architecture:** A new pure function `dedup_covered_more_specifics(all_routes)` runs once in `main()`, after own-infra exclusion and before the final write. It drops a prefix `P` only when a covering supernet `S` exists in the feed **and** `S`'s community set is a superset of `P`'s.

**Safety precondition (READ THIS):** the drop is sound only for **community-monotone** export filters — filters that are an OR of "accept if community in range", else reject. For those (`export_only_ru`, `export_blocked_lists`, `export_blocked_only`, `export_services_only`, and the `t_client` template filter), `S_comms ⊇ P_comms` guarantees any filter accepting `P` also accepts `S`, so dropping `P` changes nothing. It is **NOT** sound for the order-dependent / reject-based `export_complex_logic` example in `conf/bird.conf`: there a supernet with community `100` (RU) is *rejected* while a `{200}` more-specific under it is *accepted*, so dropping the more-specific would silently remove coverage. **Before enabling dedup, verify no `peers.d/*.conf` attaches a non-monotone filter** (the three current peers — `export_only_ru` ×2, `export_blocked_lists` — are all monotone, so today this holds). See the rollout check in Task 2 Step 0.

**Tech Stack:** Python 3.12 stdlib only (`ipaddress`), pytest. No new dependencies.

## Global Constraints

- Python stdlib only — no new third-party dependencies (matches existing `prefix_updater.py`).
- `all_routes` type is `Dict[str, Set[int]]`: CIDR string → set of community-suffix ints. Do not change this type.
- Function must be **pure** (no I/O, no global state) so it is unit-testable without network/filesystem, like `collapse_networks`.
- IPv4 only (the whole feed is IPv4).
- Self-check rule for the drop: keep `P` unless some supernet `S` (strictly less-specific, same network under `S`'s mask) satisfies `P_comms ⊆ S_comms`. Never drop a prefix whose covering supernet has a *different or narrower* community set.

---

### Task 1: `dedup_covered_more_specifics` function + unit tests

**Files:**
- Modify: `src/prefix_updater.py` (add function after `collapse_networks`, i.e. after line 276)
- Test: `tests/test_prefix_updater.py` (append new tests)

**Interfaces:**
- Consumes: `all_routes: Dict[str, Set[int]]` — CIDR → set of community suffixes (existing structure built in `main()`).
- Produces: `dedup_covered_more_specifics(all_routes: Dict[str, Set[int]]) -> int` — mutates `all_routes` in place by deleting covered more-specifics, returns the number of routes dropped.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_prefix_updater.py`:

```python
def test_dedup_drops_more_specific_when_supernet_community_superset() -> None:
    routes = {
        "10.0.0.0/24": {200},
        "10.0.0.5/32": {200},          # covered, same community -> drop
        "10.0.0.7/32": {200, 384},     # covered but {200,384} ⊄ {200} -> keep
    }
    dropped = prefix_updater.dedup_covered_more_specifics(routes)
    assert dropped == 1
    assert "10.0.0.5/32" not in routes
    assert "10.0.0.0/24" in routes
    assert "10.0.0.7/32" in routes


def test_dedup_keeps_more_specific_when_supernet_has_different_community() -> None:
    routes = {
        "10.0.0.0/24": {384},          # CDN block
        "10.0.0.5/32": {200},          # RKN host inside it; {200} ⊄ {384} -> keep
    }
    dropped = prefix_updater.dedup_covered_more_specifics(routes)
    assert dropped == 0
    assert "10.0.0.5/32" in routes


def test_dedup_drops_when_supernet_is_strict_superset() -> None:
    routes = {
        "10.0.0.0/24": {200, 384},
        "10.0.0.5/32": {200},          # {200} ⊆ {200,384} -> drop
    }
    dropped = prefix_updater.dedup_covered_more_specifics(routes)
    assert dropped == 1
    assert "10.0.0.5/32" not in routes


def test_dedup_ignores_disjoint_and_equal_prefixes() -> None:
    routes = {
        "10.0.0.0/24": {200},
        "10.1.0.0/24": {200},          # disjoint, equal length -> keep
        "10.2.0.0/24": {200, 384},     # disjoint, different comms -> keep
    }
    dropped = prefix_updater.dedup_covered_more_specifics(routes)
    assert dropped == 0
    assert len(routes) == 3


def test_dedup_handles_multi_level_nesting() -> None:
    routes = {
        "10.0.0.0/16": {200},
        "10.0.0.0/24": {200},          # covered by /16 -> drop
        "10.0.0.5/32": {200},          # covered by /16 (and /24) -> drop
    }
    dropped = prefix_updater.dedup_covered_more_specifics(routes)
    assert dropped == 2
    assert set(routes) == {"10.0.0.0/16"}


def test_dedup_is_idempotent() -> None:
    routes = {"10.0.0.0/24": {200}, "10.0.0.5/32": {200}}
    prefix_updater.dedup_covered_more_specifics(routes)
    second = prefix_updater.dedup_covered_more_specifics(routes)
    assert second == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /opt/bird2-bgp-prefix-updater && python3 -m pytest tests/test_prefix_updater.py -k dedup -v`
Expected: FAIL — `AttributeError: module 'prefix_updater' has no attribute 'dedup_covered_more_specifics'`

- [ ] **Step 3: Write minimal implementation**

Insert in `src/prefix_updater.py` immediately after `collapse_networks` (after line 276):

```python
def dedup_covered_more_specifics(all_routes: Dict[str, Set[int]]) -> int:
    """Drop a prefix when a less-specific prefix in the same feed already
    covers it AND carries a superset of its communities.

    BIRD export filters select on community ranges, so if a covering supernet
    S has every community that more-specific P has, any filter accepting P also
    accepts S. The drop is therefore safe for every peer's filter, not just one.
    A supernet with a different/narrower community set never triggers a drop.

    Mutates `all_routes` in place; returns the number of routes removed.
    """
    # Index networks by prefix length for O(prefixlen) supernet lookup.
    by_len: Dict[int, Dict[int, Set[int]]] = {}
    parsed: Dict[str, ipaddress.IPv4Network] = {}
    for cidr, comms in all_routes.items():
        net = ipaddress.IPv4Network(cidr)
        parsed[cidr] = net
        by_len.setdefault(net.prefixlen, {})[int(net.network_address)] = comms
    plens = sorted(by_len)

    drop: List[str] = []
    for cidr, net in parsed.items():
        ip = int(net.network_address)
        comms = all_routes[cidr]
        for pl in plens:
            if pl >= net.prefixlen:
                break  # only strictly less-specific prefixes can cover P
            mask = (0xFFFFFFFF << (32 - pl)) & 0xFFFFFFFF
            super_comms = by_len[pl].get(ip & mask)
            if super_comms is not None and comms <= super_comms:
                drop.append(cidr)
                break

    for cidr in drop:
        del all_routes[cidr]
    return len(drop)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /opt/bird2-bgp-prefix-updater && python3 -m pytest tests/test_prefix_updater.py -k dedup -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `cd /opt/bird2-bgp-prefix-updater && python3 -m pytest tests/test_prefix_updater.py -v`
Expected: PASS (all existing + 6 new)

- [ ] **Step 6: Commit**

```bash
cd /opt/bird2-bgp-prefix-updater
git add src/prefix_updater.py tests/test_prefix_updater.py
git commit -m "feat: dedup feed prefixes covered by a community-superset supernet"
```

---

### Task 2: Wire dedup into the generation pipeline

**Files:**
- Modify: `src/prefix_updater.py` (`main()`, right after the own-infra leak check around line 835, before the summary table at line 837)

**Interfaces:**
- Consumes: `dedup_covered_more_specifics` (Task 1); `all_routes` as it exists after `exclude_own_infra` and the leak check.
- Produces: nothing new for later code — `all_routes` is simply smaller. All downstream code (summary table, `comm_totals`, `sorted_cidrs`, BIRD write) consumes the same dict unchanged.

**Placement rationale:** Run *after* `exclude_own_infra`/leak-check (line 835) so hole-punch remainders are also considered, and a supernet that own-infra removed cannot falsely "cover" a remainder. Run *before* the summary so printed totals reflect the shipped feed.

- [ ] **Step 0: Verify no peer uses a non-monotone export filter**

Dedup is only safe for community-monotone filters (see Safety precondition in the header). Confirm no peer config attaches `export_complex_logic` (or any reject/order-dependent filter):

Run: `ssh ifp-vps02 'grep -RnE "export filter|export_complex" /etc/bird/peers.d/ 2>/dev/null'`
Expected: only `export_only_ru`, `export_blocked_lists`, `export_blocked_only`, or `export_services_only`. If `export_complex_logic` (or a custom reject-based filter) appears on any peer, STOP — do not enable dedup until that peer is migrated to a monotone filter.

- [ ] **Step 1: Add the dedup call with a log line**

In `src/prefix_updater.py`, locate the end of the own-infra leak check (the `if leaks:` block ending with `sys.exit(1)`, around line 835) and insert immediately after it, before `# Print summary table`:

```python
    # Drop more-specifics already covered by a community-superset supernet in
    # the feed (cross-source redundancy: collapse_networks runs per source, so
    # a /32 from one list inside a /24 from another is never deduplicated).
    before_dedup = len(all_routes)
    dropped = dedup_covered_more_specifics(all_routes)
    if dropped:
        print(
            f"\n  Deduplicated covered more-specifics: "
            f"{before_dedup} -> {len(all_routes)} (-{dropped})"
        )
```

- [ ] **Step 2: Syntax / import check**

Run: `cd /opt/bird2-bgp-prefix-updater && python3 -c "import importlib.util,pathlib; s=importlib.util.spec_from_file_location('pu','src/prefix_updater.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print('import ok')"`
Expected: `import ok`

- [ ] **Step 3: Dry-run against the live feed snapshot (no deploy)**

Copy the current production feed locally and verify the dedup count matches analysis (~36.5k) and that no route survives that is covered by a community-superset supernet:

Run:
```bash
cd /opt/bird2-bgp-prefix-updater
scp ifp-vps02:/etc/bird/prefixes.bird /tmp/claude-1000/-opt-bird2-bgp-prefix-updater/a7fec9f6-8461-4dd3-8a94-9b8d96305627/scratchpad/prefixes.bird
python3 - <<'EOF'
import importlib.util, ipaddress, re, pathlib
s=importlib.util.spec_from_file_location('pu','src/prefix_updater.py')
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
routes={}
for line in open('/tmp/claude-1000/-opt-bird2-bgp-prefix-updater/a7fec9f6-8461-4dd3-8a94-9b8d96305627/scratchpad/prefixes.bird'):
    g=re.match(r'route (\S+) blackhole \{ (.*)\}', line)
    if not g: continue
    # ASN-agnostic: LOCAL_AS is auto-detected from MY_AS, not always 65000.
    # A hardcoded ASN that misses would parse every comms set as empty, and
    # `set() <= anything` is True, so dedup would drop nearly everything while
    # the idempotence assert still passes — silently hiding the breakage.
    routes[g.group(1)]={int(x) for x in re.findall(r'\(\d+,\s*(\d+)\)', g.group(2))}
n0=len(routes)
dropped=m.dedup_covered_more_specifics(routes)
print(f"{n0} -> {len(routes)}  (-{dropped})")
# invariant: nothing left that a community-superset supernet still covers
left=m.dedup_covered_more_specifics(dict(routes))
assert left==0, f"second pass dropped {left}, expected 0 (idempotence broken)"
print("idempotent: OK")
EOF
```
Expected: roughly `111048 -> ~74500  (-~36500)` and `idempotent: OK`. (Exact numbers vary with the day's feed.)

- [ ] **Step 4: BIRD smoke-test the deduped output** *(only if the feed actually changed)*

The script already has `smoke_test_bird()`. Run the real updater end-to-end on the host into a temp file and let its built-in smoke test validate the config parses:

Run: `ssh ifp-vps02 'sudo /usr/bin/python3 /opt/bird2-bgp-prefix-updater/src/prefix_updater.py --help' 2>&1 | head -5`
Expected: usage text prints (confirms the deployed copy imports). Full deploy is a separate operational step, not part of this plan.

- [ ] **Step 5: Commit**

```bash
cd /opt/bird2-bgp-prefix-updater
git add src/prefix_updater.py
git commit -m "feat: run more-specific dedup in feed generation pipeline"
```

---

## Out of scope (deliberately deferred)

- **Density-based /24 aggregation** (collapse dense `/24` buckets ≥32–64 hosts). Trades a controllable amount of over-block for ~8k fewer routes. Belongs behind an opt-in flag in a separate plan — not pure-win, so it does not go in by default.
  `ponytail: dedup-only here; density aggregation is a separate opt-in feature if RIB size on clients still hurts.`

## Self-Review

- **Spec coverage:** Win #1 from the investigation (cross-source dedup of covered more-specifics) → Tasks 1–2. Win #2 (density aggregation) → explicitly deferred above. ✓
- **Placeholder scan:** No TBD/TODO; every code step shows complete code; commands have expected output. ✓
- **Type consistency:** `dedup_covered_more_specifics(all_routes: Dict[str, Set[int]]) -> int` defined in Task 1, called identically in Task 2. `all_routes` keys are CIDR strings, values `Set[int]` — matches `main()` usage (`all_routes.setdefault(p, set()).add(...)`). ✓
- **Safety scope:** the superset rule is sound only for community-monotone (accept-by-range) filters; the non-monotone `export_complex_logic` example is excluded by the precondition + Task 2 Step 0 rollout check. All three live peers use monotone filters. ✓
