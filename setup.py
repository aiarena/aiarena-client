from setuptools import setup

setup(
    name='arenaclient',
    version='0.1.13',
    packages=[
        "arenaclient",
        "arenaclient/configs",
        "arenaclient/match"
    ],
    include_package_data=True,
    install_requires=[
        "rust_arenaclient==0.1.16",
        "requests==2.24.0",
        "aiohttp==3.6.2",
        "termcolor==1.1.0",
        "psutil==5.7.2",
        "typing==3.7.4.3",
        "aiodns==2.0.0",
        "Brotli==1.0.7",
        "cchardet==2.1.6",
        "loguru==0.5.1",
    ]
)
