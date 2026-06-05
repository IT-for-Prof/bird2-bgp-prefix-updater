import importlib.util
import ipaddress
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "prefix_updater.py"
spec = importlib.util.spec_from_file_location("prefix_updater", MODULE_PATH)
assert spec is not None
prefix_updater = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(prefix_updater)


def completed_process(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(returncode=0)


def test_validate_cidr_rejects_permissive_ipv4_forms() -> None:
    assert not prefix_updater.validate_cidr("1.2.3")
    assert not prefix_updater.validate_cidr("1.2.3.4 extra")
    assert not prefix_updater.validate_cidr("010.000.000.001")


def test_cidr_and_range_collapse_still_work() -> None:
    assert prefix_updater.cidr_to_range("192.0.2.0/24") == (
        prefix_updater.ip_to_int("192.0.2.0"),
        prefix_updater.ip_to_int("192.0.2.255"),
    )
    assert prefix_updater.range_to_cidrs(
        prefix_updater.ip_to_int("198.51.100.0"),
        prefix_updater.ip_to_int("198.51.100.255"),
    ) == ["198.51.100.0/24"]
    assert prefix_updater.collapse_networks(
        ["203.0.113.0/25", "203.0.113.128/25"]
    ) == ["203.0.113.0/24"]


def test_new_ripestat_service_sources_are_present() -> None:
    sources_by_name = {source["name"]: source for source in prefix_updater.SOURCES}
    communities_by_name = {
        name: source["community_suffix"] for name, source in sources_by_name.items()
    }

    assert communities_by_name["meta_as32934"] == 380
    assert communities_by_name["twitter_as13414"] == 381
    assert communities_by_name["netflix_as2906_as40027"] == 382
    assert communities_by_name["youtube_as36040_as43515"] == 386
    assert "AS32934" in sources_by_name["meta_as32934"]["url"]
    assert "AS13414" in sources_by_name["twitter_as13414"]["url"]
    assert sources_by_name["netflix_as2906_as40027"]["require_all_urls"] is True
    assert sources_by_name["youtube_as36040_as43515"]["require_all_urls"] is True
    assert {url.rsplit("=", 1)[1] for url in sources_by_name["netflix_as2906_as40027"]["urls"]} == {
        "AS2906",
        "AS40027",
    }
    assert {url.rsplit("=", 1)[1] for url in sources_by_name["youtube_as36040_as43515"]["urls"]} == {
        "AS36040",
        "AS43515",
    }


def test_aws_json_parser_extracts_filtered_ipv4_prefixes(tmp_path: Path) -> None:
    cache_file = tmp_path / "aws.cache"
    cache_file.write_text(
        """
        {
          "prefixes": [
            {"ip_prefix": "3.10.17.128/25", "service": "CLOUDFRONT"},
            {"ip_prefix": "52.95.245.0/24", "service": "AMAZON"},
            {"ip_prefix": "13.32.0.0/15", "service": "CLOUDFRONT"}
          ],
          "ipv6_prefixes": [
            {"ipv6_prefix": "2600:9000::/28", "service": "CLOUDFRONT"}
          ]
        }
        """,
        encoding="utf-8",
    )

    prefixes = prefix_updater._parse_cached_data(
        str(cache_file),
        {
            "name": "aws_networks",
            "url": "https://ip-ranges.amazonaws.com/ip-ranges.json",
            "community_suffix": 383,
            "format": "aws_json",
            "aws_services": ["CLOUDFRONT"],
        },
    )

    assert prefixes == ["3.10.17.128/25", "13.32.0.0/15"]


def test_aws_source_is_present_with_cloudfront_filter() -> None:
    sources_by_name = {source["name"]: source for source in prefix_updater.SOURCES}

    assert sources_by_name["aws_networks"]["url"] == (
        "https://ip-ranges.amazonaws.com/ip-ranges.json"
    )
    assert sources_by_name["aws_networks"]["format"] == "aws_json"
    assert sources_by_name["aws_networks"]["community_suffix"] == 383
    assert sources_by_name["aws_networks"]["aws_services"] == ["CLOUDFRONT"]


def test_aws_json_parser_matches_configured_services_case_insensitively(
    tmp_path: Path,
) -> None:
    cache_file = tmp_path / "aws.cache"
    cache_file.write_text(
        """
        {
          "prefixes": [
            {"ip_prefix": "3.10.17.128/25", "service": "CLOUDFRONT"},
            {"ip_prefix": "52.95.245.0/24", "service": "AMAZON"}
          ]
        }
        """,
        encoding="utf-8",
    )

    prefixes = prefix_updater._parse_cached_data(
        str(cache_file),
        {
            "name": "aws_networks",
            "url": "https://ip-ranges.amazonaws.com/ip-ranges.json",
            "community_suffix": 383,
            "format": "aws_json",
            "aws_services": ["cloudfront"],
        },
    )

    assert prefixes == ["3.10.17.128/25"]


def test_bird_config_defines_aws_cloudfront_community() -> None:
    bird_config = MODULE_PATH.parents[1] / "conf" / "bird.conf"

    assert (
        "define COMM_AWS_CLOUDFRONT = (MY_AS, 383);"
        in bird_config.read_text(encoding="utf-8")
    )


def test_bird_config_rejects_own_infra_on_export() -> None:
    bird_config = (MODULE_PATH.parents[1] / "conf" / "bird.conf").read_text(
        encoding="utf-8"
    )
    # L2 safety net: own-infra defined and rejected on export. The committed
    # template uses RFC5737 documentation ranges as placeholders (no real infra
    # in this public repo); real prefixes live only in the deployed config.
    assert "define OWN_INFRA" in bird_config
    assert "192.0.2.0/24+" in bird_config
    # Peers override the template's anonymous filter with NAMED filters, so the
    # reject must guard every named export filter (5) plus the template (1).
    assert bird_config.count("if net ~ OWN_INFRA then reject;") >= 6
    # The filter peers actually use (export_only_ru) must reject own-infra first.
    ru = bird_config.split("filter export_only_ru {", 1)[1].split("}", 1)[0]
    assert "if net ~ OWN_INFRA then reject;" in ru


def test_main_repairs_missing_txt_when_bird_output_is_unchanged(
    monkeypatch: Any, tmp_path: Path
) -> None:
    bird_output = tmp_path / "prefixes.bird"
    txt_output = tmp_path / "prefixes.txt"
    bird_output.write_text(
        "route 192.0.2.0/24 blackhole { bgp_community.add((64888, 100)); };",
        encoding="utf-8",
    )

    monkeypatch.setattr(prefix_updater, "OUTPUT_BIRD", str(bird_output))
    monkeypatch.setattr(prefix_updater, "OUTPUT_TXT", str(txt_output))
    monkeypatch.setattr(
        prefix_updater,
        "SOURCES",
        [
            {
                "name": "test_source",
                "url": "https://example.test/prefixes.txt",
                "community_suffix": 100,
                "format": "text",
            }
        ],
    )
    monkeypatch.setattr(
        prefix_updater,
        "download_resource",
        lambda source, force_refresh=False: ["192.0.2.0/24"],
    )
    own_file = tmp_path / "own-infra.lst"
    own_file.write_text("203.0.113.0/24\n", encoding="utf-8")  # disjoint from test data
    monkeypatch.setattr(prefix_updater, "OWN_INFRA_FILE", str(own_file))
    monkeypatch.setattr(prefix_updater, "smoke_test_bird", lambda temp_bird_file: True)
    monkeypatch.setattr(
        prefix_updater.subprocess,
        "run",
        completed_process,
    )
    monkeypatch.setattr(prefix_updater.sys, "argv", ["prefix_updater.py"])

    prefix_updater.main()

    assert txt_output.read_text(encoding="utf-8") == "192.0.2.0/24"


def test_main_deduplicates_duplicate_aws_prefixes(monkeypatch: Any, tmp_path: Path) -> None:
    bird_output = tmp_path / "prefixes.bird"
    txt_output = tmp_path / "prefixes.txt"

    monkeypatch.setattr(prefix_updater, "OUTPUT_BIRD", str(bird_output))
    monkeypatch.setattr(prefix_updater, "OUTPUT_TXT", str(txt_output))
    monkeypatch.setattr(
        prefix_updater,
        "SOURCES",
        [
            {
                "name": "aws_networks",
                "url": "https://ip-ranges.amazonaws.com/ip-ranges.json",
                "community_suffix": 383,
                "format": "aws_json",
                "aws_services": ["CLOUDFRONT"],
            }
        ],
    )
    monkeypatch.setattr(
        prefix_updater,
        "download_resource",
        lambda source, force_refresh=False: [
            "3.10.17.128/25",
            "3.10.17.128/25",
        ],
    )
    own_file = tmp_path / "own-infra.lst"
    own_file.write_text("203.0.113.0/24\n", encoding="utf-8")  # disjoint from test data
    monkeypatch.setattr(prefix_updater, "OWN_INFRA_FILE", str(own_file))
    monkeypatch.setattr(prefix_updater, "smoke_test_bird", lambda temp_bird_file: True)
    monkeypatch.setattr(
        prefix_updater.subprocess,
        "run",
        completed_process,
    )
    monkeypatch.setattr(prefix_updater.sys, "argv", ["prefix_updater.py"])

    prefix_updater.main()

    assert bird_output.read_text(encoding="utf-8").splitlines() == [
        "route 3.10.17.128/25 blackhole { bgp_community.add((64888, 383)); };"
    ]
    assert txt_output.read_text(encoding="utf-8") == "3.10.17.128/25"


def test_require_all_urls_source_falls_back_on_partial_failure(
    monkeypatch: Any, tmp_path: Path
) -> None:
    bird_output = tmp_path / "prefixes.bird"
    txt_output = tmp_path / "prefixes.txt"
    bird_output.write_text(
        "route 198.51.100.0/24 blackhole { bgp_community.add((64888, 382)); };",
        encoding="utf-8",
    )

    source = {
        "name": "netflix_as2906_as40027",
        "urls": ["https://example.test/as2906", "https://example.test/as40027"],
        "community_suffix": 382,
        "format": "json",
        "require_all_urls": True,
    }

    def fake_download(resource: dict[str, Any], force_refresh: bool = False) -> list[str] | None:
        if resource["url"].endswith("as2906"):
            return None
        return ["203.0.113.0/24"]

    own_file = tmp_path / "own-infra.lst"
    own_file.write_text("192.0.2.0/24\n", encoding="utf-8")  # disjoint from test data
    monkeypatch.setattr(prefix_updater, "OWN_INFRA_FILE", str(own_file))
    monkeypatch.setattr(prefix_updater, "OUTPUT_BIRD", str(bird_output))
    monkeypatch.setattr(prefix_updater, "OUTPUT_TXT", str(txt_output))
    monkeypatch.setattr(prefix_updater, "SOURCES", [source])
    monkeypatch.setattr(prefix_updater, "download_resource", fake_download)
    monkeypatch.setattr(prefix_updater, "smoke_test_bird", lambda temp_bird_file: True)
    monkeypatch.setattr(
        prefix_updater.subprocess,
        "run",
        completed_process,
    )
    monkeypatch.setattr(prefix_updater.sys, "argv", ["prefix_updater.py"])

    prefix_updater.main()

    assert "198.51.100.0/24" in bird_output.read_text(encoding="utf-8")
    assert "203.0.113.0/24" not in bird_output.read_text(encoding="utf-8")


# --- own-infra exclusion -------------------------------------------------


def _own(*cidrs: str) -> list:
    return [ipaddress.ip_network(c) for c in cidrs]


def test_exclude_own_infra_drops_exact_match() -> None:
    own = _own("10.20.42.0/23")
    result = prefix_updater.exclude_own_infra({"10.20.42.0/23": {100}}, own)
    assert result == {}


def test_exclude_own_infra_drops_more_specific() -> None:
    own = _own("10.20.42.0/23")
    # /25 inside the own /23 must vanish entirely
    result = prefix_updater.exclude_own_infra({"10.20.42.128/25": {100}}, own)
    assert result == {}


def test_exclude_own_infra_hole_punches_supernet() -> None:
    own = _own("10.20.42.0/23")
    result = prefix_updater.exclude_own_infra({"10.20.0.0/16": {100, 200}}, own)
    # No remaining prefix may overlap the own block...
    own_net = own[0]
    assert all(not ipaddress.ip_network(c).overlaps(own_net) for c in result)
    # ...communities are carried onto every remainder prefix...
    assert all(comms == {100, 200} for comms in result.values())
    # ...and the remainder still covers the /16 minus the /23 (2^16 - 2^9 addrs).
    covered = sum(ipaddress.ip_network(c).num_addresses for c in result)
    assert covered == (2 ** 16) - (2 ** 9)


def test_exclude_own_infra_keeps_disjoint_prefix() -> None:
    own = _own("10.20.42.0/23")
    routes = {"8.8.8.0/24": {300}}
    assert prefix_updater.exclude_own_infra(routes, own) == {"8.8.8.0/24": {300}}


def test_exclude_own_infra_merges_duplicate_remainders() -> None:
    # Two different supernets whose remainders collide on the same CIDR must
    # have their community sets merged, not overwritten.
    own = _own("10.0.0.0/24")
    routes = {"10.0.0.0/23": {100}, "10.0.1.0/24": {200}}
    result = prefix_updater.exclude_own_infra(routes, own)
    assert result == {"10.0.1.0/24": {100, 200}}


def test_load_own_infra_fatal_when_file_missing(tmp_path: Path) -> None:
    # No hard-coded defaults (public repo): refuse to publish without inventory.
    missing = tmp_path / "nope.lst"
    with pytest.raises(SystemExit):
        prefix_updater.load_own_infra(str(missing))


def test_load_own_infra_fatal_when_file_unreadable(tmp_path: Path) -> None:
    # Path exists but cannot be read as a file (it is a directory) -> fail-closed.
    with pytest.raises(SystemExit):
        prefix_updater.load_own_infra(str(tmp_path))


def test_load_own_infra_fatal_when_file_has_no_valid_prefixes(tmp_path: Path) -> None:
    lst = tmp_path / "own-infra.lst"
    lst.write_text("# only comments\n   \nnot-an-ip\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        prefix_updater.load_own_infra(str(lst))


def test_load_own_infra_reads_file_only_no_defaults(tmp_path: Path) -> None:
    lst = tmp_path / "own-infra.lst"
    lst.write_text("# comment\n203.0.113.0/24\n\n", encoding="utf-8")
    result = set(prefix_updater.load_own_infra(str(lst)))
    assert result == {ipaddress.ip_network("203.0.113.0/24")}  # only the file entry


def test_load_own_infra_supports_inline_comments(tmp_path: Path) -> None:
    lst = tmp_path / "own-infra.lst"
    lst.write_text(
        "203.0.113.0/24  # full-line and inline comments are stripped\n"
        "198.51.100.7 # bare IP becomes /32\n"
        "   # full-line comment, indented\n",
        encoding="utf-8",
    )
    result = set(prefix_updater.load_own_infra(str(lst)))
    assert result == {
        ipaddress.ip_network("203.0.113.0/24"),
        ipaddress.ip_network("198.51.100.7/32"),
    }


def test_load_own_infra_skips_invalid_lines(tmp_path: Path) -> None:
    lst = tmp_path / "own-infra.lst"
    lst.write_text("not-an-ip\n198.51.100.7\n", encoding="utf-8")
    result = set(prefix_updater.load_own_infra(str(lst)))
    # bad line skipped, bare IP normalised to /32, no crash (one valid -> no exit)
    assert result == {ipaddress.ip_network("198.51.100.7/32")}


def test_main_excludes_own_infra_from_feed(monkeypatch: Any, tmp_path: Path) -> None:
    bird_output = tmp_path / "prefixes.bird"
    txt_output = tmp_path / "prefixes.txt"
    own_file = tmp_path / "own-infra.lst"
    own_file.write_text("10.20.42.0/23\n", encoding="utf-8")
    monkeypatch.setattr(prefix_updater, "OWN_INFRA_FILE", str(own_file))
    monkeypatch.setattr(prefix_updater, "OUTPUT_BIRD", str(bird_output))
    monkeypatch.setattr(prefix_updater, "OUTPUT_TXT", str(txt_output))
    monkeypatch.setattr(
        prefix_updater,
        "SOURCES",
        [
            {
                "name": "test_source",
                "url": "https://example.test/prefixes.txt",
                "community_suffix": 100,
                "format": "text",
            }
        ],
    )
    # Source leaks an own /24 (inside the inventory's own 10.20.42.0/23) plus a legit prefix.
    monkeypatch.setattr(
        prefix_updater,
        "download_resource",
        lambda source, force_refresh=False: ["10.20.42.0/24", "8.8.8.0/24"],
    )
    monkeypatch.setattr(prefix_updater, "smoke_test_bird", lambda temp_bird_file: True)
    monkeypatch.setattr(prefix_updater.subprocess, "run", completed_process)
    monkeypatch.setattr(prefix_updater.sys, "argv", ["prefix_updater.py"])

    prefix_updater.main()

    out = bird_output.read_text(encoding="utf-8")
    assert "10.20.42" not in out
    assert "8.8.8.0/24" in out
    assert "10.20.42" not in txt_output.read_text(encoding="utf-8")


def test_main_logs_own_infra_exclusion_even_when_holepunch_grows_feed(
    monkeypatch: Any, tmp_path: Path, capsys: Any
) -> None:
    # A supernet of an own block hole-punches into several sub-prefixes, so the
    # feed GROWS. The audit line must still report that own-infra was excluded
    # (a dict-size delta would go negative and silently skip the log).
    bird_output = tmp_path / "prefixes.bird"
    txt_output = tmp_path / "prefixes.txt"
    own_file = tmp_path / "own-infra.lst"
    own_file.write_text("10.20.42.0/23\n", encoding="utf-8")
    monkeypatch.setattr(prefix_updater, "OWN_INFRA_FILE", str(own_file))
    monkeypatch.setattr(prefix_updater, "OUTPUT_BIRD", str(bird_output))
    monkeypatch.setattr(prefix_updater, "OUTPUT_TXT", str(txt_output))
    monkeypatch.setattr(
        prefix_updater,
        "SOURCES",
        [
            {
                "name": "test_source",
                "url": "https://example.test/prefixes.txt",
                "community_suffix": 100,
                "format": "text",
            }
        ],
    )
    # Supernet of own 10.20.42.0/23 -> hole-punched into multiple sub-prefixes.
    monkeypatch.setattr(
        prefix_updater,
        "download_resource",
        lambda source, force_refresh=False: ["10.20.0.0/16"],
    )
    monkeypatch.setattr(prefix_updater, "smoke_test_bird", lambda temp_bird_file: True)
    monkeypatch.setattr(prefix_updater.subprocess, "run", completed_process)
    monkeypatch.setattr(prefix_updater.sys, "argv", ["prefix_updater.py"])

    prefix_updater.main()

    assert "Excluded own-infra" in capsys.readouterr().out


def test_main_excludes_own_infra_restored_from_old_feed(
    monkeypatch: Any, tmp_path: Path
) -> None:
    # Regression: when a source fails and old routes are restored from a
    # pre-fix prefixes.bird that still contains own-infra, exclusion must run
    # AFTER the restore so the own block does not survive.
    bird_output = tmp_path / "prefixes.bird"
    txt_output = tmp_path / "prefixes.txt"
    bird_output.write_text(
        "route 10.20.42.0/24 blackhole { bgp_community.add((64888, 100)); };\n"
        "route 198.51.100.0/24 blackhole { bgp_community.add((64888, 100)); };",
        encoding="utf-8",
    )
    own_file = tmp_path / "own-infra.lst"
    own_file.write_text("10.20.42.0/23\n", encoding="utf-8")
    monkeypatch.setattr(prefix_updater, "OWN_INFRA_FILE", str(own_file))
    monkeypatch.setattr(prefix_updater, "OUTPUT_BIRD", str(bird_output))
    monkeypatch.setattr(prefix_updater, "OUTPUT_TXT", str(txt_output))
    monkeypatch.setattr(
        prefix_updater,
        "SOURCES",
        [
            {
                "name": "test_source",
                "url": "https://example.test/prefixes.txt",
                "community_suffix": 100,
                "format": "text",
            }
        ],
    )
    # Source fails -> FALLBACK -> restore old routes (which include the own block).
    monkeypatch.setattr(
        prefix_updater,
        "download_resource",
        lambda source, force_refresh=False: None,
    )
    monkeypatch.setattr(prefix_updater, "smoke_test_bird", lambda temp_bird_file: True)
    monkeypatch.setattr(prefix_updater.subprocess, "run", completed_process)
    monkeypatch.setattr(prefix_updater.sys, "argv", ["prefix_updater.py"])

    prefix_updater.main()

    out = bird_output.read_text(encoding="utf-8")
    assert "10.20.42" not in out
    assert "198.51.100.0/24" in out
