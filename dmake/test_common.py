import re

import pytest

from dmake.common import sanitize_name


@pytest.mark.parametrize("test_input,expected", [
    ('test', 'test'),
    ('Test', 'test'),
    ('foo_bar', 'foo-bar'),
    ('Foo_BAR', 'foo-bar'),
    ('-foo', 'foo'),
    ('foo__bar', 'foo-bar'),
    ('dev-#123', 'dev--123'),
    ('foo/bar', 'foo-bar'),
])
def test_sanitize_name(test_input, expected):
    assert sanitize_name(test_input) == expected
    assert re.match(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?', sanitize_name(test_input))
