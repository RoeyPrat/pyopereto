# pyopereto
#### Opereto official Python client and CLI tool

#### Installation
```
pip install pyopereto
```
OR
```
python setup.py install
```


#### Using the command line tool
Create a file named opereto.yaml in your home directory containing Opereto access credential:
 
~/opereto.yaml
```
opereto_host: https://your_opereto_service_url
opereto_user: your_opereto_username
opereto_password: your_opereto_password
```

From the command line console, please type:
```
/>opereto -h
```


#### Using the client

```
from pyopereto.client import OperetoClient

my_client = OperetoClient(opereto_host='https://OPERETO_SERVER_URL', opereto_user='OPERETO_USERNAME', opereto_password='OPERETO_PASSWORD')
```

pyopereto wraps all common Opereto API call. To learn more about it, please check out the client code and Opereto API at: http://help.opereto.com/support/solutions/9000011679

In addition, you can learn more about automation development with pyopereto at:
http://help.opereto.com/support/solutions/articles/9000001797-developing-micro-services

