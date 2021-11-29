"""Setup script for inaira python package."""

import sys
from setuptools import setup, find_packages
import versioneer

with open('requirements.txt') as f:
    required = f.read().splitlines()

setup(name='sspeci',
      version=versioneer.get_version(),
      cmdclass=versioneer.get_cmdclass(),
      description='ODIN SSPECI',
      url='https://github.com/stfc-aeg/odin-inaira',
      author='Ashley Neaves',
      author_email='ashley.neaves@stfc.ac.uk',
      packages=find_packages('src'),
      package_dir={'': 'src'},
      install_requires=required,
      zip_safe=False,
)

