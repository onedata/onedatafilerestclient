#!/usr/bin/env python
"""Onedata REST file API client."""

from setuptools import setup

__version__ = "21.2.5.1"

CLASSIFIERS = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: System :: Filesystems",
]

with open("README.md", "rt") as f:
    DESCRIPTION = f.read()

REQUIREMENTS = ["packaging", "requests", "typing-extensions>=4.3.0"]

setup(
    name="onedatafilerestclient",
    version=__version__,
    description="Onedata REST file API client",
    long_description=DESCRIPTION,
    long_description_content_type="text/markdown",
    author="Bartek Kryza",
    author_email="bkryza@gmail.com",
    license="MIT",
    classifiers=CLASSIFIERS,
    python_requires=">=3.8",
    install_requires=REQUIREMENTS,
    packages=["onedatafilerestclient"],
    package_data={"onedatafilerestclient": ["py.typed"]},
    include_package_data=True,
    keywords=["Onedata"],
    test_suite="nose.collector",
    url="https://github.com/onedata/onedatafilerestclient",
)
