import pytest

from setup_utils import format_installs_required, is_list_of_dicts_with_keys


@pytest.mark.parametrize(
    ("value", "keys", "expected"),
    [
        pytest.param(
            [
                {"version": ">=1.0", "markers": "python_version>=3.7"},
                {"version": ">=2.0", "markers": "python_version>=3.8"},
            ],
            ["version", "markers"],
            True,
            id="Valid list with all expected keys present",
        ),
        pytest.param(
            [
                {"version": ">=1.0"},
                {"version": ">=2.0", "markers": "python_version>=3.8"},
            ],
            ["version", "markers"],
            False,
            id="Missing key in one dict",
        ),
        pytest.param(
            [{"version": ">=1.0", "markers": "python_version>=3.7"}, "not_a_dict"],
            ["version", "markers"],
            False,
            id="Non-dict element in list - string",
        ),
        pytest.param(
            {"version": ">=1.0", "markers": "python_version>=3.7"},
            ["version", "markers"],
            False,
            id="Non-list element for value",
        ),
        pytest.param([], ["version", "markers"], True, id="Empty list"),
    ]
)
def test_is_list_of_dicts_with_keys(value, keys, expected):
    assert is_list_of_dicts_with_keys(value, keys) == expected


def test_format_installs_required_successful_format():
    package_config = {
        "python": ">=3.7",
        "urllib3": ">=1.25.4",
        "requests": [
            {"version": ">=2.26.0", "markers": "python_version<'3.8'"},
            {"version": ">=2.32.0", "markers": "python_version>='3.8'"},
        ],
        "werkzeug": [
            {"version": ">2.0.0", "markers": "python_version<'3.8'"},
            {"version": ">=3.0.3", "markers": "python_version>='3.8'"},
        ],
    }
    expected_output = [
        "urllib3 (>=1.25.4)",
        "requests>=2.26.0 ; python_version<'3.8'",
        "requests>=2.32.0 ; python_version>='3.8'",
        "werkzeug>2.0.0 ; python_version<'3.8'",
        "werkzeug>=3.0.3 ; python_version>='3.8'",
    ]
    assert format_installs_required(package_config) == expected_output
