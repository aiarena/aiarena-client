from setuptools import setup

setup(
    name='arenaclient',
    version='0.2.0',
    packages=[
        "arenaclient",
        "arenaclient/configs",
        "arenaclient/match"
    ],
    include_package_data=True,
    install_requires=[
        "rust_arenaclient==0.2.1",
        "requests==2.25.1",
        "aiohttp==3.7.4",
        "termcolor==1.1.0",
        "psutil==5.8.0",
        "typing==3.7.4.3",
        "aiodns==3.0.0",
        "Brotli==1.0.9",
        "cchardet==2.1.7",
        "loguru==0.6.0",
    ]
)
