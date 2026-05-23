import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any


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
