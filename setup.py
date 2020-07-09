from setuptools import setup

setup(
    name='arenaclient',
    version='0.1',
    packages=[
        "arenaclient",
        "arenaclient/configs",
        "arenaclient/match"
    ],
    include_package_data=True,
    install_requires=[
        "rust_arenaclient==0.1.5",
        "requests==2.24.0",
        "aiohttp==3.6.2",
        "termcolor==1.1.0",
        "psutil==5.7.0",
        "typing==3.7.4.1",
        "aiodns>=2.0.0",
        "Brotli",
        "cchardet",
        "loguru",
    ]
)
