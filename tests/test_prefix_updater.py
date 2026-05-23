import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "prefix_updater.py"
spec = importlib.util.spec_from_file_location("prefix_updater", MODULE_PATH)
assert spec is not None
prefix_updater = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(prefix_updater)


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
    communities_by_name = {
        source["name"]: source["community_suffix"] for source in prefix_updater.SOURCES
    }

    assert communities_by_name["meta_as32934"] == 380
    assert communities_by_name["twitter_as13414"] == 381
    assert communities_by_name["netflix_as2906_as40027"] == 382
    assert communities_by_name["youtube_as36040_as43515"] == 386
