from setuptools import setup, find_packages

with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name="peacock",
    version="0.1",
    author="Diego Llanes",
    author_email="peacock@diegollanes.com",
    description="A simple command line tool to manage your dotfiles",
    long_description=long_description,
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "peacock=peacock.peacock:main",
        ],
    },
)
