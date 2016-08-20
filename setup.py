from setuptools import setup, find_packages

setup(
    name='pyopereto',
    version='1.0.24',
    author='Dror Russo',
    author_email='dror.russo@opereto.com',
    description='Opereto Python Client & Development Utils',
    url = 'https://github.com/opereto/pyopereto',
    download_url = 'https://github.com/opereto/pyopereto/archive/1.0.24.tar.gz',
    keywords = [],
    classifiers = [],
    packages = ['pyopereto'],
    package_data = {},
    install_requires=[
        "requests > 2.7.0",
        "pyyaml"
    ]
)
