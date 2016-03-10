# pyopereto
#### Opereto Python client and development utils

#### Installation
```
pip install pyopereto
```
OR
```
python setup.py install
```
#### Using the client
```
from pyopereto import OperetoClient

my_client = OperetoClient(opereto_host='https://OPERETO_SERVER_URL', opereto_user='OPERETO_USERNAME', opereto_password='OPERETO_PASSWORD')

## run a process
pid = my_client.create_process(service='my_service', title='running a process of my service', agent='my_agent_name')

## wait for process to end with success
if not my_client.is_success(pid):
    exit my_client.FAILURE
....
....
exit my_client.SUCCESS
```

#### Uploading & Running Services during developmet
##### prepare the dev environment
Before you start developing microservices, please add the a new file called config.yaml to pyopereto scripts directory containing the following credentials:
```
opereto_host: https://your_opereto_service_url
opereto_user: your_opereto_username
opereto_password: your_opereto_password
aws_access_key: your_opereto_s3_dev_repo_access_key
aws_secret_key: your_opereto_s3_dev_repo_secret_key
aws_s3_bucket: your_opereto_s3_dev_repo_bucket_name

```

##### service directory structure
The standard service directory structure contains the following files:
```
~/my_service_name/
    service.yaml        # service specification yaml
    service.sam.json    # service agents mapping (optional)
    service.md          # service readme file (markdown, optional) 

    + any executable files/directories
```
The name of the directory is the unique identifier (or name) of the service in Opereto.
It is a good practice to have all service directories in the same directory in your source repository. For intance:
```
~/myproject/
    microservices/
        service_1/
            ...
            ...
        service2/
            ...
            ...
```
In some cases, we want to keep a few services in the same directory. In such cases, all relevant files must start with the service name. For instance:
```
~/myproject/microservices/
    my_service_1.yaml        
    my_service_1.sam.json    
    my_service_1.md      
    my_service_2.yaml    
    my_service_2.sam.json
    my_service_2.md      
    
    + any executable files/directories
```

##### upload your dev services
```
python upload_service.py -d /path/to/your/service/directory [-s service_name]

```
A service name has to be provided only if there are few services in the same directory. If not specified, the name of the directory will be used as the service name.

##### run services in development mode (sendbox)
```
python run_service.py -s service_name [-t "your process title"] [-a agent_name]

```
If agent is not specified, Opereto will select an agent that matches the service agent mapping.
If title is not specified, a default process title will be provided by Opereto.
