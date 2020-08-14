import pytest
import semver

from dmake.commands.release import is_valid_bump


@pytest.mark.parametrize("prev_version_str,next_version_str,is_valid", [
    ('0.2.0', '0.3.0-rc1', True),
    ('0.2.0', '0.2.1', True),
    ('0.2.0', '0.3.0', True),
    ('0.2.0', '1.2.0', False),
    ('0.2.0', '0.2.2', False),
    ('0.8.2', '0.8.3-dev1', True),
    ('0.8.3-dev1', '0.8.3-dev2', True),
    ('0.8.3', '0.8.3-dev1', False),
    ('1.0.0-alpha', '1.0.0-alpha.1', True),
    ('1.0.0-alpha.1', '1.0.0-beta', True),
    ('1.0.0-beta+0', '1.0.0-alpha.1+45', False)
])
def test_valid_bump(prev_version_str, next_version_str, is_valid):
    prev_version = semver.VersionInfo.parse(prev_version_str)
    next_version = semver.VersionInfo.parse(next_version_str)
    assert is_valid_bump(prev_version, next_version) == is_valid
