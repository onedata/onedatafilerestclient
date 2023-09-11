#!/usr/bin/env python
"""Onedata REST file API client."""

from setuptools import setup

__version__ = '21.02.4.rc1'

CLASSIFIERS = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python",
    "Programming Language :: Python :: 3.5",
    "Programming Language :: Python :: 3.6",
    "Programming Language :: Python :: 3.7",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Topic :: System :: Filesystems",
]

with open("README.md", "rt") as f:
    DESCRIPTION = f.read()

REQUIREMENTS = ["requests"]

setup(name="onedatafilerestclient",
      author="Bartek Kryza",
      author_email="bkryza@gmail.com",
      classifiers=CLASSIFIERS,
      description="Onedata REST file API client",
      install_requires=REQUIREMENTS,
      license="MIT",
      long_description=DESCRIPTION,
      packages=["onedatafilerestclient"],
      keywords=["Onedata"],
      test_suite="nose.collector",
      url="https://github.com/onedata/onedatafilerestclient",
      version=__version__)
