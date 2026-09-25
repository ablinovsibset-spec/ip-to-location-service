from scripts.compare_ips import (
    are_synonyms,
    mismatch_note,
    name_verdict,
    normalize_name,
)


def test_matching_names_case_insensitive():
    assert name_verdict("Maharashtra", "success", "maharashtra") == "match"


def test_whitespace_normalized():
    assert name_verdict("  Tamil   Nadu ", "success", "Tamil Nadu") == "match"


def test_iso_difference_is_ignored():
    assert name_verdict("Maharashtra", "success", "Maharashtra") == "match"
    assert name_verdict("Karnataka", "success", "Karnataka") == "match"


def test_ipapi_fail_is_mismatch():
    assert name_verdict("Maharashtra", "fail", None) == "mismatch"
    assert name_verdict("Maharashtra", "fail", "") == "mismatch"


def test_empty_region_name_after_success_is_mismatch():
    assert name_verdict("Maharashtra", "success", None) == "mismatch"
    assert name_verdict("Maharashtra", "success", "") == "mismatch"


def test_empty_service_name_is_mismatch():
    assert name_verdict(None, "success", "Maharashtra") == "mismatch"
    assert name_verdict("", "success", "Maharashtra") == "mismatch"


def test_different_names_mismatch():
    assert name_verdict("Maharashtra", "success", "Delhi") == "mismatch"


def test_normalize_name():
    assert normalize_name("  Tamil   Nadu ") == "tamil nadu"
    assert normalize_name(None) is None
    assert normalize_name("   ") is None


def test_delhi_synonyms():
    assert are_synonyms("Delhi", "National Capital Territory of Delhi")
    assert mismatch_note("Delhi", "National Capital Territory of Delhi") == "synonym"


def test_puducherry_synonyms():
    assert are_synonyms("Puducherry", "Union Territory of Puducherry")
    assert are_synonyms("Pondicherry", "Puducherry")


def test_real_geo_mismatch_is_not_synonym():
    assert not are_synonyms("Puducherry", "Tamil Nadu")
    assert not are_synonyms("Ladakh", "Jammu and Kashmir")
    assert mismatch_note("Sikkim", "West Bengal") == ""


def test_identical_names_are_not_synonym_flag():
    assert not are_synonyms("Delhi", "Delhi")
    assert mismatch_note("Delhi", "Delhi") == ""
