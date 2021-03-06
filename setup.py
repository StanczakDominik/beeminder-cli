"""setup.py file for beeminder CLI."""
from setuptools import setup

setup(
    name="beeminder",
    version="0.1",
    py_modules=["beeminder"],
    install_requires=["Click", "requests", "colorama"],
    entry_points="""
        [console_scripts]
        beeminder=beeminder:beeminder
    """,
    python_requires=">=3.7",
)
