# pyopereto
#### A simple python wrapper for Opereto API 

##### Installation
```
pip install pyopereto
```

##### Using the client
```
from pyopereto import OperetoClient

my_client = OperetoClient(opereto_host='https://OPERETO_SERVER_URL', opereto_user='OPERETO_USERNAME', opereto_password='OPERETO_PASSWORD')

## run a process
pid = my_client.create_process(service='my_service', title='running a process of my service', agent='my_agent_name')

## wait for process to end with success
if not my_client.success(pid):
    return my_client.FAILURE
....
....
return my_client.SUCCESS
```

##### Run the tests 
The tests directory contains additional usage examples. To run all tests, please do the following:
1. pip install pytest
2. Add your opereto credentials in the test.conf file
3. In the tests directory run: pytest



##### Uploading & Running Services during developmet
```
## upload to Opereto server
python microservice.py -d path/to/my/service/directory

## upload to Opereto server + run it on my agent
python microservice.py -d path/to/my/service/directory --run -a my_agent
```
