from setuptools import setup
import os

HOME_DIR = os.path.expanduser("~")

setup(
    name='pyopereto',
    version='1.0.35',
    author='Dror Russo',
    author_email='dror.russo@opereto.com',
    description='Opereto Python Client',
    url = 'https://github.com/opereto/pyopereto',
    download_url = 'https://github.com/opereto/pyopereto/archive/1.0.35.tar.gz',
    keywords = [],
    classifiers = [],
    packages = ['pyopereto'],
    package_data = {},
    scripts=['scripts/opereto.py', 'scripts/opereto.bat', 'scripts/opereto.sh'],
    install_requires=[
        "requests > 2.7.0",
        "pyyaml",
        "docopt==0.6.2",
        "colorlog==2.10.0"
    ]
)
