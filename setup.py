#!/usr/bin/env python
"""Setup script for Urban Mobility Analytics."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="urban-mobility-analytics",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Real-time traffic and weather monitoring dashboard for Malta routes",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/urban-mobility-analytics",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.13",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering :: GIS",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.10",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "urban-mobility-collect=src.route_extraction:main",
            "urban-mobility-migrate=src.migration:main",
            "urban-mobility-analyze=src.analytics:main",
            "urban-mobility-train=train_models:main",
        ],
    },
    include_package_data=True,
    package_data={
        "src": ["models/trained/*.pkl"],
    },
)
