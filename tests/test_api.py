import pytest

from lilac2.api import (
    _unquote_item,
    _add_into_array,
)

@pytest.mark.parametrize('shell_str, python_str', [
  ('"abc"', 'abc'),
  ("'abc'", 'abc'),
])
def test_unquote_item(shell_str, python_str):
  assert _unquote_item(shell_str) == python_str

@pytest.mark.parametrize('line, extra_elements, line_expected', [
  ("some_array=()", ["ab", "bc"], "some_array=('ab' 'bc')"),
  ("some_array=('ab', 'bc')", ["cd"], "some_array=('ab' 'bc' 'cd')"),
  ('''some_array=("ab" "bc")''', ["cd"], "some_array=('ab' 'bc' 'cd')"),
  ('''some_array=("ab" 'bc')''', ["cd"], "some_array=('ab' 'bc' 'cd')"),
  ('''some_array=("ab"''', ["cd"], "some_array=('ab' 'cd'"),
])
def test_add_into_array(line, extra_elements, line_expected):
  assert _add_into_array(line, extra_elements) == line_expected

