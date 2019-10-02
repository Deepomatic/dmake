import re

import pytest

from dmake.common import sanitize_name, sanitize_name_unique


@pytest.mark.parametrize("test_input,expected", [
    ('test', 'test'),
    ('Test', 'test'),
    ('foo_bar', 'foo-bar'),
    ('Foo_BAR', 'foo-bar'),
    ('-foo', 'foo'),
    ('#foo', 'foo'),
    ('foo__bar', 'foo-bar'),
    ('dev-#123', 'dev--123'),
    ('foo/bar', 'foo-bar'),
])
def test_sanitize_name_kubernetes(test_input, expected):
    assert sanitize_name(test_input) == expected
    assert re.match(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?', sanitize_name(test_input))

@pytest.mark.parametrize("test_input,expected", [
    ('test', 'test'),
    ('Test', 'Test'),
    ('foo_Bar', 'foo_Bar'),
    ('-foo', 'foo'),
    ('_foo', 'foo'),
    ('.foo', 'foo'),
    ('#foo', 'foo'),
    ('foo#bar', 'foo-bar'),
    ('foo##bar', 'foo-bar'),
    ('foo/bar#baz', 'foo-bar-baz'),
])
def test_sanitize_name_docker(test_input, expected):
    assert sanitize_name(test_input, mode='docker') == expected
    assert re.match(r'[a-zA-Z0-9][a-zA-Z0-9_.-]+', sanitize_name(test_input, mode='docker'))

def test_sanitize_name_unique():
    assert sanitize_name_unique('foo_bar', mode='docker') == 'foo_bar', "When no sanitation is needed it should return identity"
    assert sanitize_name_unique('foo/bar', mode='docker') != sanitize_name_unique('foo#bar', mode='docker'), "Same sanitization should still be unique"
    assert sanitize_name_unique('foo/bar', mode='docker') == sanitize_name_unique('foo/bar', mode='docker'), "Sanitation should be stable"
