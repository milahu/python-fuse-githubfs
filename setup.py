#!/usr/bin/env python3
from setuptools import setup, find_packages

setup(
    name="githubfs",
    author="Peter Kerpedjiev",
    author_email="pkerpedjiev@gmail.com",
    packages=["githubfs"],
    entry_points={"console_scripts": ["githubfs = githubfs.__main__:main"]},
    url="https://github.com/milahu/githubfs",
    description="FUSE filesystem for Github",
    license="MIT",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    install_requires=["boto3", "diskcache", "fusepy", "requests", "tenacity"],
    version="0.4.12",
)
