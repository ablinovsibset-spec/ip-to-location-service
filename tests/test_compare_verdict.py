from scripts.compare_ips import iso_verdict, strip_country_prefix


def test_matching_codes_after_prefix_strip():
    assert iso_verdict("IN-MH", "success", "MH") == "match"


def test_name_difference_is_ignored():
    # Names are not arguments to the verdict helper on purpose.
    assert iso_verdict("IN-MH", "success", "MH") == "match"
    assert iso_verdict("IN-KA", "success", "KA") == "match"


def test_ipapi_fail_is_mismatch():
    assert iso_verdict("IN-MH", "fail", None) == "mismatch"
    assert iso_verdict("IN-MH", "fail", "") == "mismatch"


def test_empty_region_after_success_is_mismatch():
    assert iso_verdict("IN-MH", "success", None) == "mismatch"
    assert iso_verdict("IN-MH", "success", "") == "mismatch"


def test_different_codes_mismatch():
    assert iso_verdict("IN-MH", "success", "DL") == "mismatch"


def test_strip_country_prefix():
    assert strip_country_prefix("IN-MH") == "MH"
    assert strip_country_prefix("US-CA") == "CA"
    assert strip_country_prefix(None) is None
