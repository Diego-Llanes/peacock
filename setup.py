from setuptools import setup, find_packages

setup(
    name="peacock",
    version="0.1",
    # packages=find_packages(),
    entry_points={
        "console_scripts": [
            "peacock=peacock.peacock:main",
        ],
    },
)
