#!/usr/bin/env python
# -*- coding: utf-8 -*-
import io
import os
import sys
from shutil import rmtree

from setuptools import find_packages, setup, Command


REQUIRED = [
    'requests', 'lxml', 'toposort'
]

here = os.path.abspath(os.path.dirname(__file__))

setup(
    name='lilac',
    version='0.1.0',
    description='',
    long_description='',
    author='lilydjwg',
    author_email='lilydjwg@gmail.com',
    python_requires='>=3.4.0',
    url='https://github.com/archlinuxcn/lilac',
    packages=find_packages(exclude=('tests',)),
    scripts= ['lilac', 'recv_gpg_keys', 'pypi2pkgbuild'],
    install_requires=REQUIRED,
    include_package_data=True,
    package_data={
        '': ['config.ini.sample'],
    },
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
)
