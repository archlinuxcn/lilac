#!/usr/bin/env python3
from setuptools import find_packages, setup

setup(
  name = 'archlinuxcn-lilac',
  use_scm_version = True,
  description = 'The build bot for archlinuxcn',
  author = 'lilydjwg',
  author_email = 'lilydjwg@gmail.com',
  python_requires = '>=3.7.0',
  url = 'https://github.com/archlinuxcn/lilac',
  packages = find_packages(exclude=('tests',)),
  py_modules = ['lilaclib'],
  scripts = ['lilac', 'recv_gpg_keys'],
  setup_requires = ['setuptools_scm'],
  # See README.md
  install_requires = [
    'requests', 'lxml', 'toposort', 'PyYAML', 'pyalpm', 'structlog', 'python_prctl',
  ],
  include_package_data = True,
  package_data = {
    'lilac2': ['aliases.yaml'],
  },
  classifiers = [
    'Programming Language :: Python',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.7',
  ],
)
