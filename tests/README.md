## Opereto test suite for core packages (py.test based)
In general, this suite will run via opereto as part of the continuous testing cycle. For manual execution on your dev environment, please follow these steps:

#### libraries and configuration 

```
pip install -U pytest
pip install pyopereto
```

Add a file named arguments.yaml (that will be loaded by the pyopereto client if executed via Opereto) to the root directory of this repo containing the following:
```
opereto_host: OPERETO_HOST
opereto_user: OPERETO_USERNAME
opereto_password: OPERETO_PASSWORD
opereto_agent: AGENT_NAME
sut_environment: ENVIRONMENT_NAME

```

#### Usage
run all tests:
```
py.test -v
```

run all tests of a given file:
```
py.test test_server_process_handling.py
```

run specific tests from specific files:
```
py.test tests_directory/foo.py tests_directory/bar.py -k 'test_001 or test_some_other_test'
```

for more command options:
```
py.test --help
```
