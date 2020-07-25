#!/usr/bin/env python

from pathlib import Path
from setuptools import setup, find_packages

project_root = Path(__file__).resolve().parent

with project_root.joinpath('requirements.txt').open('r', encoding='utf-8') as f:
    requirements = f.read().splitlines()

with project_root.joinpath('readme.rst').open('r', encoding='utf-8') as f:
    long_description = f.read()

about = {}
with project_root.joinpath('lib', '__version__.py').open('r', encoding='utf-8') as f:
    exec(f.read(), about)


setup(
    name=about['__title__'],
    version=about['__version__'],
    author=about['__author__'],
    author_email=about['__author_email__'],
    description=about['__description__'],
    long_description=long_description,
    url=about['__url__'],
    project_urls={'Source': about['__url__']},
    packages=find_packages(),
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
    ],
    python_requires='~=3.8',
    install_requires=requirements,
    extras_require={'dev': ['pre-commit', 'ipython']}
)
