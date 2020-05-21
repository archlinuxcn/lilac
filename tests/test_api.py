import pytest

from lilac2.api import (
    _unquote_item,
    _add_into_array,
    _allow_update_aur_repo,
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

# commits are from https://aur.archlinux.org/{pkgname}.git
@pytest.mark.parametrize('pkgname, commit_sha1, expected', [
  ('mxnet-git', 'b628fc716d23ae88373c6bd1089409297ccb2a38', False),
  ('mxnet-git', 'c80336319e1a3e60178d815a48690e90d2a0c889', False),
  ('mxnet-git', 'c88817c10e95f9d9afd7928b973504c4085b4b6c', True),
  ('nodejs-web-ext', 'e4d4a1c33026d221ebf6570cc0a33c99dc4b1d9d', True),
  ('python-onnxruntime', '7447a82a3fac720bbb85ba5cea5d99f7d6920690', False),
])
def test_allow_update_aur_repo(pkgname, commit_sha1, expected):
  with open(f'tests/fixtures/{pkgname}-{commit_sha1}.diff') as f:
    diff = f.read()
  assert _allow_update_aur_repo(pkgname, diff) == expected
