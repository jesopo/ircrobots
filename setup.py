from setuptools import find_namespace_packages, setup

with open("README.md", "r") as fh:
    long_description = fh.read()
with open("VERSION", "r") as version_file:
    version = version_file.read().strip()
with open("requirements.txt", "r") as requirements_file:
    install_requires = requirements_file.read().splitlines()

setup(
    name="ircrobots",
    version=version,
    author="jesopo",
    author_email="pip@jesopo.uk",
    description="Asyncio IRC bot framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jesopo/ircrobots",
    packages=["ircrobots"] + find_namespace_packages(include=["ircrobots.*"]),
    package_data={"ircrobots": ["py.typed"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Operating System :: POSIX",
        "Operating System :: Microsoft :: Windows",
        "Topic :: Communications :: Chat :: Internet Relay Chat"
    ],
    python_requires='>=3.6',
    install_requires=install_requires
)
