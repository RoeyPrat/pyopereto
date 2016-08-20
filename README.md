# pyopereto
#### Opereto official Python client and development scripts

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
from pyopereto.client import OperetoClient

my_client = OperetoClient(opereto_host='https://OPERETO_SERVER_URL', opereto_user='OPERETO_USERNAME', opereto_password='OPERETO_PASSWORD')
```


You can create a file named arguments.yaml in your development environment specifying Opereto access credential. 
```
opereto_host: https://your_opereto_service_url
opereto_user: your_opereto_username
opereto_password: your_opereto_password
```

In that case, you may call the client with no arguments as follows:

```
from pyopereto.client import OperetoClient

my_client = OperetoClient()

```

When Opereto run services on remote servers, it creates this credentials file. For that reason, you should use the second option (w\o passing the credentials) in your service code.  

PyOpereto wraps all common Opereto API call. To learn more about it, please check out the client code and Opereto API at: http://help.opereto.com/support/solutions/9000011679

In addition, you can learn more about automation development with pyopereto at: http://help.opereto.com/support/solutions/articles/9000001797-developing-micro-services

