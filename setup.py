#!/usr/bin/env python

import platform
from pathlib import Path
from setuptools import setup, find_packages

project_root = Path(__file__).resolve().parent
long_description = project_root.joinpath('readme.rst').read_text('utf-8')

about = {}
with project_root.joinpath('lib', '__version__.py').open('r', encoding='utf-8') as f:
    exec(f.read(), about)

requirements = [
    'requests_client@ git+https://github.com/dskrypa/requests_client',
    'ds_tools@ git+https://github.com/dskrypa/ds_tools',
    'flask',
    'jinja2',
    'werkzeug',
    'lxml',
    'gevent',
    'flask_socketio' if platform.system() == 'Windows' else 'gunicorn',
]

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
