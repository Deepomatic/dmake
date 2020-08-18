import pytest

from dmake.commands.release import is_valid_bump, tag_to_version


@pytest.mark.parametrize("prev_version_str,next_version_str,is_valid", [
    # Bump patch
    ('0.2.0', '0.2.1', True),
    ('0.2.0', '0.2.2', False),  # 0.2.1 is skipped

    # Bump minor
    ('0.2.0', '0.3.0', True),
    ('0.2.0', '0.3.0-rc1', True),  # pre-release of a new minor version

    # Bump major
    ('0.2.2', '1.0.0', True),
    ('0.2.2-dev1', '0.2.2', True),  # finalize version
    ('0.2.2-dev1', '1.0.0', False),  # 0.2.2 is skipped
    ('0.2.2', '1.0.0-dev1', True),  # pre-release of a new major version
    ('0.2.0', '1.2.0', False),  # 1.0.0 and 1.1.0 are skipped

    # Bump prerelease
    ('1.0.0-alpha.1', '1.0.0-beta', True),
    ('0.8.3', '0.8.4-dev1', True),
    ('0.8.3', '0.8.3-dev1', False),  # Need to bump major or minor or patch before new pre-release
    ('1.0.0-beta+0', '1.0.0-alpha.1+45', False),  # alphabetical order is not respected

    # Bump build
    ('1.0.0-alpha', '1.0.0-alpha.1', True),
    ('1.0.0-beta+12', '1.0.0-beta+56', False),  # Equal precedence, '1.0.0-beta+12' == '1.0.0-beta+56'
])
def test_valid_bump(prev_version_str, next_version_str, is_valid):
    prev_version = tag_to_version(prev_version_str)
    next_version = tag_to_version(next_version_str)
    assert is_valid_bump(prev_version, next_version) == is_valid
