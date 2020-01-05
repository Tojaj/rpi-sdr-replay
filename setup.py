#!/usr/bin/env python3
"""Setup script"""

from setuptools import find_packages, setup

VERSION = '0.0.1'

setup(
    name='rpi-sdr-replay',
    description='Command line tool for migration/backup of releases from PDC',
    version=VERSION,
    license='GPLv3+',
    url='https://github.com/Tojaj/rpi-sdr-replay',
    download_url='https://github.com/Tojaj/rpi-sdr-replay/releases',
    author='Tomas Mlcoch',
    author_email='xtojaj@gmail.com',

    install_requires=['bluedot'],
    packages=find_packages(exclude=["tests"]),
    scripts=["rpi-sdr-replay"],

    tests_require=['mock', 'bluedot'],
    test_suite='tests',

    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Education',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Topic :: Utilities',
        'Topic :: Security',
        'Topic :: Communications :: Ham Radio'
    ]
)

