from setuptools import setup

VERSION = '1.0.38'

setup(
    name='pyopereto',
    version=VERSION,
    author='Dror Russo',
    author_email='dror.russo@opereto.com',
    description='Opereto Python Client',
    url = 'https://github.com/opereto/pyopereto',
    download_url = 'https://github.com/opereto/pyopereto/archive/%s.tar.gz'%VERSION,
    keywords = [],
    classifiers = [],
    packages = ['pyopereto'],
    package_data = {},
    entry_points = {
        'console_scripts': ['opereto=pyopereto.command_line:main']
    },
    install_requires=[
        "requests > 2.7.0",
        "pyyaml",
        "docopt",
        "colorlog"
    ]
)
