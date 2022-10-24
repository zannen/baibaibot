import setuptools

VERSION = "0.0.1"

setuptools.setup(
    name="BaiBaiBot",
    version=VERSION,
    author="ZanNen",
    author_email="",
    description="A simple Kraken trading bot",
    long_description="",
    long_description_content_type="text/markdown",
    url="https://github.com/zannen/baibaibot",
    packages=setuptools.find_packages(),
    package_data={"baibaibot": ["py.typed"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[],
    setup_requires=["wheel"],
    zip_safe=False,
)
