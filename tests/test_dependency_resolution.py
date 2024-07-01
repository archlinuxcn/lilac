from collections import namedtuple
from pathlib import Path

from lilac2.packages import DependencyManager, get_dependency_map

def test_dependency_map():
  depman = DependencyManager(Path('.'))
  Info = namedtuple('Info', ['repo_depends', 'repo_makedepends'])
  lilacinfos = {
    'A': Info(['B'], ['C']),
    'B': Info(['D'], ['C']),
    'C': Info([],    ['E']),
    'D': Info([],    []),
    'E': Info(['D'], []),
    'F': Info([],    ['C', 'D']),
    'G': Info([],    ['F']),
  }
  expected_all = {
    'A': { 'B', 'C', 'D', 'E' },
    'B': { 'C', 'D', 'E' },
    'C': { 'D', 'E' },
    'D': set(),
    'E': { 'D' },
    'F': { 'C', 'D', 'E' },
    'G': { 'C', 'D', 'E', 'F' },
  }
  expected_build = {
    'A': { 'B', 'C', 'D' },
    'B': { 'C', 'D' },
    'C': { 'D', 'E' },
    'D': set(),
    'E': { 'D' },
    'F': { 'C', 'D' },
    'G': { 'F' },
  }

  res_all, res_build = get_dependency_map(depman, lilacinfos)
  def parse_map(m):
    return { key: { val.pkgdir.name for val in s } for key, s in m.items() }
  assert parse_map(res_all) == expected_all
  assert parse_map(res_build) == expected_build
