import os,sys
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor
from datetime import datetime
import requests
import json
import yaml
import time
from functools import wraps as _wraps
from re import sub

try:
    from urllib.request import urlopen
    from urllib.parse import urlparse, urlencode
except ImportError:
    from urlparse import urlparse
    from urllib import urlopen
    from urllib import urlencode

try:
    requests.packages.urllib3.disable_warnings()
except AttributeError:
    pass
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except:
    pass

import logging
FORMAT = '%(asctime)s: [%(name)s] [%(levelname)s] %(message)s'
logging.basicConfig(stream=sys.stdout, format=FORMAT, level=logging.ERROR)
logger = logging.getLogger('pyopereto')
logging.getLogger("pyopereto").setLevel(logging.INFO)
if os.environ.get('opereto_debug_mode'):
    logging.getLogger("pyopereto").setLevel(logging.DEBUG)

process_result_statuses = ['success', 'failure', 'error', 'timeout', 'terminated', 'warning']
process_running_statuses = ['in_process', 'registered']
process_statuses = process_result_statuses + process_running_statuses


class OperetoClientError(Exception):
    """
    Exceptions thrown by OperetoClient methods are wrapped by this class, /
    taking from the inner exception the message and error code
    """
    def __init__(self, message, code=500):
        self.message = message
        self.code = code
    def __str__(self):
        return self.message


def apicall(f):

    @_wraps (f)
    def f_call(*args, **kwargs):
        for i in range(3):
            try:
                rv = f(*args, **kwargs)
                return rv
            except OperetoClientError as e:
                logger.debug('API Call failed: {}'.format(str(e)))
                if e.code>=500 and i<2:
                    time.sleep(1)
                else:
                    raise e
            except requests.exceptions.RequestException as e:
                if i<2:
                    time.sleep(1)
                else:
                    raise e
    return f_call


class OperetoClient(object):
    """
    OperetoClient is the class exposing PyOpereto's client and CLI tool methods.
    Exceptions raised by this class methods are wrapped in an OperetoClientError exception class
    """

    SUCCESS = 0
    ERROR = 1
    FAILURE = 2
    WARNING = 3

    def __init__(self, **kwargs):
        self.input=kwargs
        work_dir = os.getcwd()
        home_dir = os.path.expanduser("~")

        def get_credentials(file):
            try:
                with open(file, 'r') as f:
                    if file.endswith('.json'):
                        self.input = json.loads(f.read())
                    else:
                        self.input = yaml.load(f.read(), Loader=yaml.FullLoader)
            except Exception as e:
                raise OperetoClientError('Failed to parse %s: %s'%(file, str(e)))

        if not set(['opereto_user', 'opereto_password', 'opereto_host']) <= set(self.input):
            if os.path.exists(os.path.join(work_dir,'arguments.json')):
                get_credentials(os.path.join(work_dir,'arguments.json'))
            elif os.path.exists(os.path.join(work_dir,'arguments.yaml')):
                get_credentials(os.path.join(work_dir,'arguments.yaml'))
            elif os.path.exists(os.path.join(home_dir,'opereto.yaml')):
                get_credentials(os.path.join(home_dir,'opereto.yaml'))

        ## TEMP: fix in agent
        for item in list(self.input.keys()):
            try:
                if self.input[item]=='null':
                    self.input[item]=None
                else:
                    value = json.loads(self.input[item])
                    if isinstance(value, dict):
                        self.input[item]=value
            except:
                pass

        self.logger = logger
        if not set(['opereto_user', 'opereto_password', 'opereto_host']) <= set(self.input):
            raise OperetoClientError('Missing one or more credentials required to connect to opereto center.')

        ## connect to opereto center
        self.session = None


    def _get_client_releases(self):
        response = requests.get('https://pypi.org/pypi/pyopereto/json')
        if response.status_code<299:
            return response.json()['releases'].keys()


    def _get_pids(self, pids=[]):
        if isinstance(pids, str):
            pids = [self._get_pid(pids)]
        if not pids:
            raise OperetoClientError('Process identifier(s) must be provided.')
        return pids


    def _get_pid(self, pid=None):
        actual_pid = pid or self.input.get('pid')
        if not actual_pid:
            raise OperetoClientError('Process identifier must be provided.')
        return actual_pid


    def _connect(self):
        if not self.session:
            self.session = requests.Session()
            self.session.auth = (self.input['opereto_user'], self.input['opereto_password'])
            try:
                response = self.session.post('%s/login'%self.input['opereto_host'], verify=False)
                self.logger.debug(response)
                if response.status_code>201:
                    try:
                        error_message = response.json()['message']
                    except:
                        error_message=response.reason
                    raise OperetoClientError('Failed to login to opereto server [%s]: %s'%(self.input['opereto_host'], error_message))
            except Exception as e:
                self.session=None
                raise e


    def logout(self):
        if self.session:
            self.session.get(self.input['opereto_host']+'/logout', verify=False)


    def _process_response(self, r, error=None):

        try:
            response_json = r.json()
        except:
            response_json={'status': 'failure', 'message': r.reason}

        self.logger.debug('Response: [{}] {}'.format(r.status_code, response_json))

        if response_json:
            if response_json['status']!='success':
                response_message = response_json.get('message') or ''
                if error:
                    response_message = error + ':\n' + response_message
                if response_json.get('errors'):
                    response_message += response_json['errors']
                raise OperetoClientError(message=response_message, code=r.status_code)
            elif 'data' in response_json:
                return response_json['data']


    def _call_rest_api(self, method, url, data={}, error=None, **kwargs):

        self.logger.debug('Request: [{}]: {}'.format(method, url))
        if data:
            self.logger.debug('Request Data: {}'.format(data))

        self._connect()
        if method=='get':
            r = self.session.get(self.input['opereto_host']+url, verify=False)
        elif method=='put':
            r = self.session.put(self.input['opereto_host']+url, verify=False, data=json.dumps(data))
        elif method=='post':
            if kwargs.get('files'):
                r = self.session.post(self.input['opereto_host']+url, verify=False, files=kwargs['files'])
            else:
                r = self.session.post(self.input['opereto_host']+url, verify=False, data=json.dumps(data))
        elif method=='delete':
            r = self.session.delete(self.input['opereto_host']+url, verify=False)
        else:
            raise OperetoClientError(message='Invalid request method.', code=500)

        return self._process_response(r, error=error)


    #### GENERAL ####
    @apicall
    def hello(self):
        """
        hello(self)

        | Checks if Opereto Server is up and running.

        :Example:
        .. code-block:: python

           opereto_client = OperetoClient()
           opereto_client.hello()
        """
        return self._call_rest_api('get', '/hello', error='Failed to get response from the opereto server')


    #### MICROSERVICES & VERSIONS ####
    @apicall
    def search_services(self, start=0, limit=100, filter={}, **kwargs):
        """
        search_services(start=0, limit=100, filter={}, **kwargs)

        | Search for Opereto services, in Services data and properties

        :Parameters:
        * *start* (`int`) -- start index to retrieve from. Default is 0
        * *limit* (`int`) -- Maximum number of entities to retrieve. Default is 100
        * *filter* (`object`) -- Free text search pattern (checks in service data and properties)

        :return: List of search results

        :Example:
        .. code-block:: python

           filter = {'generic': 'testing_'}
           search_result = opereto_client.search_services(filter=filter)

        """
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/services', data=request_data, error='Failed to search services')


    @apicall
    def get_service(self, service_id):
        """
        get_service(service_id)

        | Get a service meta data (id, audit log, type, etc.) information.

        :Parameters:
        * *service_id* (`string`) -- Identifier of an existing service
        :return: Service meta data

        :Example:
        .. code-block:: python

            service_meta_data = opereto_client.get_service(serviceId)

        """
        return self._call_rest_api('get', '/services/'+service_id, error='Failed to fetch service information')

    @apicall
    def get_service_version(self, service_id, mode='production', version='default'):
        """
        get_service_version(service_id, mode='production', version='default')

        | Get a specific version details of a given service. Opereto will try to fetch the requested service version. If not found, it will return the default production version. The "actual_version" field of the returned JSON indicates what version of the service is returned. If the actual version is null, it means that this service does not have any version at all. To make it operational, you will have to import or upload a default version.

        :Parameters:
        * *service_id* (`string`) -- Identifier of an existing service
        * *mode* (`string`) -- development/production. Default is production
        * *version* (`string`) -- version of the service ("default" is the default.

        :return: json service version details

        :Example:
        .. code-block:: python

           service_version = opereto_client.get_service_version(serviceId, mode='development', version='111')
        """
        return self._call_rest_api('get', '/services/'+service_id+'/'+mode+'/'+version, error='Failed to fetch service information')


    @apicall
    def verify_service(self, service_id, specification=None, description=None, agent_mapping=None):
        """
        verify_service(service_id, specification=None, description=None, agent_mapping=None)

        | Verifies validity of service yaml

        :Parameters:
        * *service_id* (`string`) -- Identifier of an existing service
        * *specification* (`string`) -- service specification yaml
        * *description* (`string`) -- service description written in text or markdown style
        * *agent_mapping* (`string`) -- agents mapping specification

        :return: json service version details

        :Example:
        .. code-block:: python

           spec = {
               "type": "action",
               "cmd": "python -u run.py",
               "timeout": 600,
               "item_properties": [
                    {"key": "key1", "type": "text", "value": "value1", "direction": "input"},
                    {"key": "key2", "type": "boolean", "value": True, "direction": "input"}
                 ]
              }
           if opereto_client.verify_service ('hello_world', specification=spec)['errors'] == []:
              result = True

        """
        request_data = {'id': service_id}
        if specification:
            request_data['spec']=specification
        if description:
            request_data['description']=description
        if agent_mapping:
            request_data['agents']=agent_mapping
        return self._call_rest_api('post', '/services/verify', data=request_data, error='Service [%s] verification failed'%service_id)


    
    def modify_service(self, service_id, type):
        """
        modify_service(service_id, type)

        | Modifies a service type (action, container, etc.)

        :Parameters:
        * *service_id* (`string`) -- Identifier of an existing service
        * *type* (`string`) -- service type

        :return: Service modification metadata (service id, type, modified date, versions

        :Example:
        .. code-block:: python

           service_modification_metadata = opereto_client.modify_service ('myService', 'container')
           if service_modification_metadata['type'] == 'container'
              print 'service type of {} changed to container'.format('myService')

        """
        request_data = {'id': service_id, 'type': type}
        return self._call_rest_api('post', '/services', data=request_data, error='Failed to modify service [%s]'%service_id)


    def upload_service_version(self, service_zip_file, mode='production', service_version='default', service_id=None, **kwargs):
        """
        upload_service_version(service_zip_file, mode='production', service_version='default', service_id=None, **kwargs)

        Upload a service version to Opereto

        :Parameters:
        * *service_zip_file* (`string`) -- zip file location containing service and service specification
        * *mode* (`string`) -- production/development (default is production)
        * *service_version* (`string`) -- Service version
        * *service_id* (`string`) -- Service Identifier

        :Keywords args:
        * *comment* (`string`) -- comment

        :Example:
        .. code-block:: python

           opereto_client.upload_service_version(service_zip_file=zip_action_file+'.zip', mode='production', service_version='111')

        """
        file_size = os.stat(service_zip_file).st_size
        files = {'service_file': open(service_zip_file,'rb')}
        url_suffix = '/services/upload/%s'%mode
        if mode=='production':
            url_suffix+='/'+service_version
        if service_id:
            url_suffix+='/'+service_id
        if kwargs:
            url_suffix=url_suffix+'?'+urlencode(kwargs)

        def my_callback(monitor):
            read_bytes = monitor.bytes_read
            percentage = int(float(read_bytes)/float(file_size)*100)
            if percentage>95:
                percentage=95

            sys.stdout.write('\r{}% Uploaded out of {} Bytes'.format(percentage, file_size))
            sys.stdout.flush()

        e = MultipartEncoder(
            fields=files
        )
        m = MultipartEncoderMonitor(e, my_callback)
        self._connect()
        r  = self.session.post(self.input['opereto_host']+url_suffix, verify=False, data=m)
        sys.stdout.write('\r100% Uploaded out of {} Bytes\n'.format(file_size))
        sys.stdout.flush()
        return self._process_response(r)


    def import_service_version(self, repository_json, mode='production', service_version='default', service_id=None, **kwargs):
        """
        import_service_version(repository_json, mode='production', service_version='default', service_id=None, **kwargs)

        Imports a service version into Opereto from a remote repository (GIT, SVN, AWS S3, any HTTPS repository)

        :Parameters:
        * *repository_json* (`object`) -- repository_json
        :Example of repository JSON:
            .. code-block:: json

                #GIT source control
                {
                    "repo_type": "git",
                    "url": "git@bitbucket.org:my_account_name/my_project.git",
                    "branch": "master",
                    "ot_dir": "mydir"
                }

                #SVN
                {
                    "repo_type": "svn",
                    "url": "svn://myhost/myrepo",
                    "username": "OPTIONAL_USERNAME",
                    "password": "OPTIONAL_PASSWORD",
                    "ot_dir": "my_service_dir"
                }

                # Any HTTP based remote storage

                {
                    "repo_type": "http",
                    "url": "https://www.dropbox.com/s/1234567890/MyFile.zip?dl=0",
                    "username": "OPTIONAL_PASSWORD",
                    "ot_dir": "my_service_dir"
                }

                # AWS S3 Storage

                {
                    "repo_type": "s3",
                    "bucket": "my_bucket/my_service.zip",
                    "access_key": "MY_ACCESS_KEY",
                    "secret_key": "MY_SECRET_KEY",
                    "ot_dir": "my_service_dir"
                }

        * *mode* (`string`) -- production/development (default is production)
        * *service_version* (`string`) -- Service version
        * *service_id* (`string`) -- Service version


        :return: status - success/failure

        :Example:
        .. code-block:: python

            # for GIT
           repository_json = {
                "branch": "master",
                "ot_dir": "microservices/hello_world",
                "repo_type": "git",
                "url": "https://github.com/myCompany/my_services.git"
            }

            opereto_client.import_service_version(repository_json, mode='production', service_version='default', service_id=self.my_service2)

        """
        request_data = {'repository': repository_json, 'mode': mode, 'service_version': service_version, 'id': service_id}
        url_suffix = '/services'
        if kwargs:
            url_suffix=url_suffix+'?'+urlencode(kwargs)
        return self._call_rest_api('post', url_suffix, data=request_data, error='Failed to import service')

    
    def delete_service(self, service_id):
        """
        delete_service(service_id)

        Deletes a Service from Opereto

        :Parameters:
        * *service_id* (`string`) -- Service Identifier

        :return: status: success/failure

         :Example:
        .. code-block:: python

           opereto_client.delete_service('my_service_id')

        """

        return self._call_rest_api('delete', '/services/'+service_id, error='Failed to delete service')



    def delete_service_version(self, service_id , service_version='default', mode='production'):
        """
        delete_service(service_id, service_version='default', mode='production')

        Deletes a Service version from Opereto

        :Parameters:
        * *service_id* (`string`) -- Service identifier
        * *service_version* (`string`) -- Service version. Default is 'default'
        * *mode* (`string`) -- development/production. Default is production

        :return: success/failure

        :Example:
        .. code-block:: python

           opereto_client.delete_service('my_service_id')

        """
        return self._call_rest_api('delete', '/services/'+service_id+'/'+mode+'/'+service_version, error='Failed to delete service')


    @apicall
    def list_development_sandbox(self):
        """
        list_development_sandbox(self)

        List all services in the current user's development sandbox

        :return: List of sandbox services ids. e.g: ['testing_hello_world', 'pytest_execution']

        """
        return self._call_rest_api('get', '/services/sandbox', error='Failed to list sandbox services')


    
    def purge_development_sandbox(self):
        """
        purge_development_sandbox(self)

        Deletes all services from the current user's development sandbox.

        :return: success/failure

        """
        return self._call_rest_api('delete', '/services/sandbox', error='Failed to delete sandbox services')



    #### ENVIRONMENTS ####
    @apicall
    def search_environments(self, start=0, limit=100, filter={}, **kwargs):
        """
        search_environments(start=0, limit=100, filter={}, **kwargs)

        Search environments

        :Parameters:
        * *start* (`int`) -- start index to retrieve from. Default is 0
        * *limit* (`int`) -- maximum number of entities to retrieve. Default is 100
        * *filter* (`object`) -- free text search pattern (checks in environment data and properties)

        :return: List of search results or empty list
        """
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/environments', data=request_data, error='Failed to search environments')


    @apicall
    def get_environment(self, environment_id):
        """
        get_environment(environment_id)

        Get environment general info.


        :param String environment_id: Identifier of an existing environment
        :return: environment data

        """
        return self._call_rest_api('get', '/environments/'+environment_id, error='Failed to fetch environment [%s]'%environment_id)

    @apicall
    def verify_environment_scheme(self, environment_type, environment_topology):
        """
        verify_environment_scheme(environment_type, environment_topology)

        Verifies json scheme of an environment

        :Parameters:

        * *environment_type* (`string`) -- Topology identifier
        * *environment_topology* (`object`) -- Environment json to validate

        :return: Success or errors in case the verification failed

        :Return Example:
        .. code-block:: json

            # verification failure
            {'errors': ['Topology key cluster_name is missing in environment specification'], 'agents': {}, 'success': False, 'warnings': []}

            # verification success
            {'errors': [], 'agents': {}, 'success': True, 'warnings': []}

        :Example:
        .. code-block:: python

            environment_topology =
            {
                  "cluster_name": "k8s-clusbbe9",
                  "config_file": {
                    "contexts": [
                      {
                        "name": "my-context"
                      }
                    ],
                    "clusters": [
                      {
                        "name": "k8s-clusbbe9"
                      }
                    ]
                  }
            }
            environment = opereto_client.verify_environment_scheme(environment_type = 'myTopology', environment_topology = environment_topology)

        """
        request_data = {'topology_name': environment_type, 'topology': environment_topology}
        return self._call_rest_api('post', '/environments/verify', data=request_data, error='Failed to verify environment.')

    @apicall
    def verify_environment(self, environment_id):
        """
        verify_environment(environment_id)

        Verifies validity of an existing environment

        :Parameters:

        * *environment_id* (`string`) -- Environment identifier

        :return: Success or errors in case the verification failed

        :Return Example:
        .. code-block:: json

            # verification failure
            {'errors': ['Topology key cluster_name is missing in environment specification'], 'agents': {}, 'success': False, 'warnings': []}

            # verification success
            {'errors': [], 'agents': {}, 'success': True, 'warnings': []}

        """
        request_data = {'id': environment_id}
        return self._call_rest_api('post', '/environments/verify', data=request_data, error='Failed to verify environment.')

    
    def create_environment(self, topology_name, topology={}, id=None, **kwargs):
        """
        create_environment(topology_name, topology={}, id=None, **kwargs)

        Create a new environment

        :Parameters:

        * *topology_name* (`string`) -- The topology identifier. Must be provided to create an environment.
        * *topology* (`object`) -- Topology data (must match the topology json schema)
        * *id* (`object`) -- The environment identifier. If none provided when creating environment, Opereto will automatically assign a unique identifier.

        :return: id of the created environment

        """
        request_data = {'topology_name': topology_name,'id': id, 'topology':topology, 'add_only':True}
        request_data.update(**kwargs)
        return self._call_rest_api('post', '/environments', data=request_data, error='Failed to create environment')

    
    def modify_environment(self, environment_id, **kwargs):
        """
        modify_environment(environment_id, **kwargs)

        Modifies an existing environment

        :Parameters:
        * *environment_id* (`string`) -- The environment identifier

        Keywords args:
        The variables to change in the environment

        :return: id of the created environment

        """
        request_data = {'id': environment_id}
        request_data.update(**kwargs)
        return self._call_rest_api('post', '/environments', data=request_data, error='Failed to modify environment')

    
    def delete_environment(self, environment_id):
        """
        delete_environment(environment_id)

        Delete an existing environment

        :Parameters:
        * *environment_id* (`string`) -- The environment identifier to delete

        """
        return self._call_rest_api('delete', '/environments/'+environment_id, error='Failed to delete environment [%s]'%environment_id)


    #### AGENTS ####

    @apicall
    def search_agents(self, start=0, limit=100, filter={}, **kwargs):
        """
        search_agents(start=0, limit=100, filter={}, **kwargs)

        Search agents

        :Parameters:
        * *start* (`int`) -- start index to retrieve from. Default is 0
        * *limit* (`int`) -- maximum number of entities to retrieve. Default is 100
        * *filter* (`object`) -- free text search pattern (checks in agent data and properties)

        :return: List of search results or empty list

        :Example:
        .. code-block:: python

           filter = {'generic': 'my Agent'}
           search_result = opereto_client.search_agents(filter=filter)

        """
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/agents', data=request_data, error='Failed to search agents')

    @apicall
    def get_agents(self, agent_id):
        """
        get_agents(agent_id)

        Get agent general details

        :Parameters:
        * *agent_id* (`string`) -- Agent identifier

        :return: Agent general details

        """
        return self._call_rest_api('get', '/agents/'+agent_id, error='Failed to fetch agent details.')


    @apicall
    def get_agent_properties(self, agent_id):
        """
        get_agent_properties(agent_id)

        Get agent properties separated to custom properties defined by the user and built-in properties provided by Opereto.

        :Parameters:
        * *agent_id* (`string`) -- Agent identifier

        :return: Agent general details

        :Example:
        .. code-block:: python

            >>> my_agent_properties = opereto_client.get_agent_properties('my_agent_id')
            >>> print (my_agent_properties)

            {'builtin':
                {'system.arch': 'amd64', 'agent.user': 'Ariel', 'network': '{lo=[/127.0.0.1/8 [/127.255.255.255], /0:0:0:0:0:0:0:1/128 [null]], net6=[], net5=[], net7=[], eth11=[], eth10=[], eth13=[], net0=[], wlan1=[/da:0:0:0:29dc:fe33:4234:30bd%19/64 [null]], eth12=[], wlan0=[/10.100.222.423/24 [/10.100.222.423], /fa:0:0:0:29dc:fe33:4234:30bd%19/64 [null]], eth15=[], net2=[], eth14=[], net1=[], net4=[], net3=[], wlan6=[], wlan7=[], wlan8=[], wlan9=[], wlan2=[/fe80:0:0:0:455d:390b:c559:f259%20/64 [null]], wlan3=[], wlan4=[], wlan5=[], eth9=[], eth3=[], eth4=[], eth1=[], eth2=[], eth7=[], eth8=[], eth5=[/fe80:0:0:0:2807:b110:c4fb:835b%11/64 [null]], eth6=[], eth0=[], wlan12=[], wlan11=[], wlan10=[], ppp0=[], wlan15=[], wlan14=[], wlan13=[]}', 'agent.user.home': 'C:\\Users\\myuser', 'opereto_agent_version': '1.1.44', 'hostname': 'DESKTOP-', 'total.space': '237.9 GiB', 'agent.home': 'C:\\Users\\myuser\\opereto-agent\\target', 'available.processors': '4', 'free.space': '140.3 GiB', 'os.name': 'windows 8.1', 'system.version': '6.3'},
                'custom': {'agent_current_env': 'env1'}}


        """
        return self._call_rest_api('get', '/agents/'+agent_id+'/properties', error='Failed to fetch agent [%s] properties'%agent_id)

    @apicall
    def get_all_agents(self):
        """
        get_all_agents()

        Get all agents

        :return: list of existing agents

        """
        return self._call_rest_api('get', '/agents/all', error='Failed to fetch agents')


    
    def modify_agent_property(self, agent_id, key, value):
        """
        modify_agent_property(agent_id, key, value)

        Modifies a single single property of an agent. If the property does not exists then it is created as a custom property.

        :Parameters:
        * *agent_id* (`string`) -- Identifier of an existing agent
        * *key* (`string`) -- Key of a property to change
        * *value* (`string`) -- New Value of the property to change

        :Example:
        .. code-block:: python

           opereto_client.modify_agent_property('my_agent_id', 'agent_new_property', 'agent value')

        """
        return self._call_rest_api('post', '/agents/'+agent_id+'/properties', data={key: value}, error='Failed to modify agent [%s] property [%s]'%(agent_id,key))


    
    def modify_agent_properties(self, agent_id, key_value_map={}):
        """
        modify_agent_properties(agent_id, key_value_map={})

        Modify properties of an agent. If properties do not exists, they will be created

        :Parameters:
        * *agent_id* (`string`) -- Identifier of an existing agent
        * *key_value_map* (`object`) -- Key value map of properties to change
        * *value* (`string`) -- New Value of the property to change

        :Example:
        .. code-block:: python

           opereto_client.modify_agent_properties('my_agent_id', {"mykey": "myvalue", "mykey2": "myvalue2"})

        """
        return self._call_rest_api('post', '/agents/'+agent_id+'/properties', data=key_value_map, error='Failed to modify agent [%s] properties'%agent_id)


    
    def create_agent(self, agent_id=None, **kwargs):
        """
        create_agent(agent_id=None, **kwargs)

        | Creates an agent based on the identifier provided. \
        | The agent will become online when a real agent will connect using this identifier. \
        | However, in most cases, the agent entity is created automatically when a new agent connects to opereto. \

        :Parameters:
        * *agent_id* (`string`) -- Identifier of an existing agent
        :Keywords args:
        * *name* (`string`) -- Display name to show in the UI
        * *description* (`string`) -- A textual description of the agent
        * *permissions* (`object`) -- Permissions on the agent
            * *owners* (`array`) -- List of Opereto usernames that may modify and delete the agent
            * *owners* (`array`) -- List of Opereto usernames that may run services on the agent
        :return: id of the generated agent

        :Example:
        .. code-block:: python

           opereto_client = OperetoClient()
           opereto_client.create_agent(agent_id='xAgent', name='My new agent', description='A new created agent to be called from X machines')
        """
        request_data = {'id': agent_id, 'add_only':True}
        request_data.update(**kwargs)
        return self._call_rest_api('post', '/agents'+'', data=request_data, error='Failed to create agent')


    
    def modify_agent(self, agent_id, **kwargs):
        """
        modify_agent(agent_id, **kwargs)

        | Modifies agent information (like name)

        :Parameters:
        * *agent_id* (`string`) -- Identifier of an existing agent

         :Example:
        .. code-block:: python

           opereto_client = OperetoClient()
           opereto_client.modify_agent('agentId', name='my new name')
        """
        request_data = {'id': agent_id}
        request_data.update(**kwargs)
        return self._call_rest_api('post', '/agents'+'', data=request_data, error='Failed to modify agent [%s]'%agent_id)


    @apicall
    def get_agent(self, agent_id):
        """
        get_agent(agent_id)

        Get agent general details

        :Parameters:
        * *agent_id* (`string`) -- Identifier of an existing agent

         :Example:
        .. code-block:: python

            >>> agent_is_online = opereto_client.get_agent('my_agent_id')['online']
            >>> print (my_agent_properties)

            # example of return value
            False

        """
        return self._call_rest_api('get', '/agents/'+agent_id, error='Failed to fetch agent [%s] status'%agent_id)

    @apicall
    def get_agent_status(self, agent_id):
        """
        get_agent_status(agent_id)

        Get agent status. Returns the agent information with the 'online' property (true or false)

        :Parameters:
        * *agent_id* (`string`) -- Identifier of an existing agent

        :Example:
        .. code-block:: python

            my_agent_status = opereto_client.get_agent_status('my_agent_id')['online']

        """
        return self.get_agent(agent_id)

    
    def delete_agent(self, agent_id):
        """
        delete_agent(agent_id)

        Deletes an agent

        :Parameters:
        * *agent_id* (`string`) -- Identifier of an existing agent

        """

        return self._call_rest_api('delete', '/agents/'+agent_id, error='Failed to delete agent [%s] status'%agent_id)

    #### PROCESSES ####

    def create_process(self, service, agent=None, title=None, mode=None, service_version=None, **kwargs):
        """
        create_process(service, agent=None, title=None, mode=None, service_version=None, **kwargs)

        Registers a new process or processes

        :Parameters:
        * *service* (`string`) -- Service which process will be started
        * *agent* (`string`) -- a valid value may be one of the following: agent identifier, agent identifiers (list) : ["agent_1", "agent_2"..], "all", "any"
        * *title* (`string`) -- Title for the process
        * *mode* (`string`) -- production/development
        * *service_version* (`string`) -- Version of the service to execute

        :Keywords args:
        Json value map containing the process input properties

        :return: process id

        :Example:
        .. code-block:: python

           process_properties = {"my_input_param" : "1"}
           pid = opereto_client.create_process(service='simple_shell_command', title='Test simple shell command service', agent=opereto_client.input['opereto_agent'], **process_properties)

        """
        self.logger.debug('Creating a new process..')
        if not agent:
            agent = self.input.get('opereto_agent')

        if not mode:
            mode=self.input.get('opereto_execution_mode') or 'production'
        if not service_version:
            service_version=self.input.get('opereto_service_version')

        request_data = {'service_id': service, 'agents': agent, 'mode': mode, 's_version':service_version}
        if title:
            request_data['name']=title

        if self.input.get('pid'):
            request_data['pflow_id']=self.input.get('pid')

        request_data.update(**kwargs)
        ret_data= self._call_rest_api('post', '/processes', data=request_data, error='Failed to create a new process')

        if not isinstance(ret_data, list):
            raise OperetoClientError(str(ret_data))

        pid = ret_data[0]
        message = 'New process created for service [%s] [pid = %s] '%(service, pid)
        if agent:
            message += ' [agent = %s]'%agent
        self.logger.info(message)

        return str(pid)


    
    def rerun_process(self, pid, title=None, agent=None):
        """
        rerun_process(pid, title=None, agent=None)

        Reruns a process

        :Parameters:
        * *pid* (`string`) -- Process id to rerun
        * *title* (`string`) -- Title for the process
        * *agent* (`string`) -- a valid value may be one of the following: agent identifier, agent identifiers (list) : ["agent_1", "agent_2"..], "all", "any"

        :return: process id

        """
        request_data = {}
        if title:
            request_data['name']=title
        if agent:
            request_data['agents']=agent

        if self.input.get('pid'):
            request_data['pflow_id']=self.input.get('pid')

        ret_data= self._call_rest_api('post', '/processes/'+pid+'/rerun', data=request_data, error='Failed to create a new process')

        if not isinstance(ret_data, list):
            raise OperetoClientError(str(ret_data))

        new_pid = ret_data[0]
        message = 'Re-executing process [%s] [new process pid = %s] '%(pid, new_pid)
        self.logger.info(message)
        return str(new_pid)


    def modify_process_properties(self, key_value_map={}, pid=None):
        """
        modify_process_properties(key_value_map={}, pid=None)

        Modify process output properties.
        Please note that process property key provided must be declared as an output property in the relevant service specification.

        :Parameters:
        * *key_value_map* (`object`) -- key value map with process properties to modify
        * *pid* (`string`) -- Identifier of an existing process

        :Example:
        .. code-block:: python

           process_output_properties = {"my_output_param" : "1"}
           pid = opereto_client.create_process(service='simple_shell_command', title='Test simple shell command service')
           opereto_client.modify_process_properties(process_output_properties, pid)

        """
        pid = self._get_pid(pid)
        request_data={"properties": key_value_map}
        return self._call_rest_api('post', '/processes/'+pid+'/output', data=request_data, error='Failed to output properties')

    
    def modify_process_property(self, key, value, pid=None):
        """
        modify_process_property(key, value, pid=None)

        Modify process output property.
        Please note that the process property key provided must be declared as an output property in the relevant service specification.

        :Parameters:
        * *key* (`String`) -- key of property to modify
        * *key* (`value`) -- value of property to modify
        * *pid* (`string`) -- Identifier of an existing process

        :Example:
        .. code-block:: python

           pid = opereto_client.create_process(service='simple_shell_command', title='Test simple shell command service')
           opereto_client.modify_process_property("my_output_param", "1" , pid)

        """
        pid = self._get_pid(pid)
        request_data={"key" : key, "value": value}
        return self._call_rest_api('post', '/processes/'+pid+'/output', data=request_data, error='Failed to modify output property [%s]'%key)

    
    def modify_process_summary(self, pid=None, text='', append=False):
        """
        modify_process_summary(pid=None, text='')

        Modifies the summary text of the process execution

        :Parameters:
        * *key* (`pid`) -- Identifier of an existing process
        * *key* (`text`) -- summary text
        * *append* (`boolean`) -- True to append to summary. False to override it.

        """
        pid = self._get_pid(pid)

        if append:
            current_summary =  self.get_process_info(pid).get('summary') or ''
            modified_text = current_summary + '\n' + text
            text = modified_text

        request_data = {"id": pid, "data": str(text)}
        return self._call_rest_api('post', '/processes/'+pid+'/summary', data=request_data, error='Failed to update process summary')


    
    def stop_process(self, pids=[], status='success'):
        """
        stop_process(pids, status='success')

        Stops a running process

        :Parameters:
        * *pid* (`string`) -- Identifier of an existing process
        * *result* (`string`) -- the value the process will be terminated with. Any of the following possible values:  success , failure , error , warning , terminated

        """
        if status not in process_result_statuses:
            raise OperetoClientError('Invalid process result [%s]'%status)
        pids = self._get_pids(pids)
        for pid in pids:
            self._call_rest_api('post', '/processes/'+pid+'/terminate/'+status, error='Failed to stop process')


    @apicall
    def get_process_status(self, pid=None):
        """
        get_process_status(pid=None)

        Get current status of a process

        :Parameters:
        * *pid* (`string`) -- Identifier of an existing process

        """
        pid = self._get_pid(pid)
        return self._call_rest_api('get', '/processes/'+pid+'/status', error='Failed to fetch process status')


    @apicall
    def get_process_flow(self, pid=None):
        """
        get_process_flow(pid=None)

        Get process in flow context. The response returns a sub-tree of the whole flow containing the requested process, its direct children processes, and all ancestors.
        You can navigate within the flow backword and forward by running this call on the children or ancestors of a given process.

        :Parameters:
        * *pid* (`string`) -- Identifier of an existing process

        """
        pid = self._get_pid(pid)
        return self._call_rest_api('get', '/processes/'+pid+'/flow', error='Failed to fetch process information')


    @apicall
    def get_process_rca(self, pid=None):
        """
        get_process_rca(pid=None)

        Get the RCA tree of a given failed process. The RCA tree contains all failed child processes that caused the failure of the given process.

        :Parameters:
        * *pid* (`string`) -- Identifier of an existing process

        """
        pid = self._get_pid(pid)
        return self._call_rest_api('get', '/processes/'+pid+'/rca', error='Failed to fetch process information')


    @apicall
    def get_process_info(self, pid=None):
        """
        get_process_info(pid=None)

        Get process general information.

        :Parameters:
        * *pid* (`string`) -- Identifier of an existing process

        """

        pid = self._get_pid(pid)
        return self._call_rest_api('get', '/processes/'+pid, error='Failed to fetch process information')

    @apicall
    def get_process_log(self, pid=None, start=0, limit=1000):
        """
        get_process_log(pid=None, start=0, limit=1000

        Get process logs

        :Parameters:
        * *pid* (`string`) -- Identifier of an existing process
        * *start* (`string`) -- start index to retrieve logs from
        * *limit* (`string`) -- maximum number of entities to retrieve

        :return: Process log entries

        """
        pid = self._get_pid(pid)
        data = self._call_rest_api('get', '/processes/'+pid+'/log?start={}&limit={}'.format(start,limit), error='Failed to fetch process log')
        return data['list']

    @apicall
    def send_process_log(self, pid, log_entries=[]):
        """
        send_process_log(pid=None, log_entries=[{'text'='This is my log', level=''}])

        Send process logs

        :Parameters:
        * *pid* (`string`) -- Identifier of an existing process
        * *log_entries* (`list`) -- start index to retrieve logs from

        :return: Process log entries

        """
        timestamp = int(int((datetime.utcnow() - datetime(1970, 1, 1)).total_seconds()))* 1000
        log_data = []
        for entry in log_entries:
            if not entry.get('level'):
                entry['level']='INFO'
            entry['timestamp']=timestamp
            log_data.append(entry)

        request_data = {'id': pid, 'data': log_data}
        res = self._call_rest_api('post', '/processes/'+pid+'/log', data=request_data, error='Failed to send process log')
        return res


    @apicall
    def search_process_log(self, pid, filter={}, start=0, limit=1000):
        """
        search_process_log(pid, filter={}, start=0, limit=1000)

        Search in process logs

        :Parameters:
        * *pid* (`string`) -- Identifier of an existing process
        * *start* (`int`) -- start index to retrieve from. Default is 0
        * *limit* (`int`) -- maximum number of entities to retrieve. Default is 100
        * *filter* (`object`) -- free text search pattern (checks in process log data)

        :return: Count of records found and list of search results or empty list

        :Example:
        .. code-block:: python

           filter = {'generic': 'my product param'}
           search_result = opereto_client.search_globals(filter=filter)
           if len(search_result) > 0:
              print(search_result)
        """
        pid = self._get_pid(pid)
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        return self._call_rest_api('post', '/processes/' + pid + '/log/search', data=request_data,
                                    error='Failed to search in process log')

    ## deprecated
    def get_process_property(self, pid=None, name=None):
        pid = self._get_pid(pid)
        return self.get_process_properties(pid, name)


    @apicall
    def get_process_properties(self, pid=None, name=None, verbose=False):
        """
        get_process_properties(pid=None, name=None)

        Get process properties (both input and output properties)

        :Parameters:
        * *pid* (`string`) -- Identifier of an existing process
        * *name* (`string`) -- optional - Property name

        """
        pid = self._get_pid(pid)
        url = '/processes/'+pid+'/properties'
        if verbose:
            url+='?verbose=true'
        res = self._call_rest_api('get', url, error='Failed to fetch process properties')
        if name:
            try:
                return res[name]
            except KeyError as e:
                raise OperetoClientError(message='Invalid property [%s]'%name, code=404)
        else:
            return res


    @apicall
    def wait_for(self, pids=[], status_list=process_result_statuses):
        """
        wait_for(pids=[], status_list=process_result_statuses)

        Waits for a process to finish

        :Parameters:
        * *pids* (`list`) -- list of processes waiting to be finished
        * *status_list* (`list`) -- optional - List of statuses to wait for processes to finish with

        :Example:
        .. code-block:: python

           pid = opereto_client.create_process(service='simple_shell_command', title='Test simple shell command service')
           opereto_client.wait_for([pid], ['failure', 'error'])
           opereto_client.rerun_process(pid)

        """
        results={}
        pids = self._get_pids(pids)
        for pid in pids:
            interval=1
            while(True):
                try:
                    stat = self._call_rest_api('get', '/processes/'+pid+'/status', error='Failed to fetch process [%s] status'%pid)
                    if stat in status_list:
                        results[pid]=stat
                        break
                    time.sleep(interval)
                    if interval<5:
                        interval+=1
                except requests.exceptions.RequestException as e:
                    # reinitialize session using api call decorator
                    self.session=None
                    raise e
        return results


    def _status_ok(self, status, pids=[]):
        pids = self._get_pids(pids)
        self.logger.info('Waiting that the following processes %s will end with status [%s]..'%(str(pids), status))
        statuses = self.wait_for(pids)
        if not statuses:
            return False
        for pid,stat in list(statuses.items()):
            if stat!=status:
                self.logger.error('But it ended with status [%s]'%stat)
                return False
        return True


    def wait_to_start(self, pids=[]):
        """
        wait_to_start(pids=[])

        Wait for processes to start

        :Parameters:
        * *pids* (`list`) -- list of processes to wait to start

        """
        actual_pids = self._get_pids(pids)
        return self.wait_for(pids=actual_pids, status_list=process_result_statuses+['in_process'])


    def wait_to_end(self, pids=[]):
        """
        wait_to_end(pids=[])

        Wait for processes to finish

        :Parameters:
        * *pids* (`list`) -- list of processes to wait to finish

        """
        actual_pids = self._get_pids(pids)
        return self.wait_for(pids=actual_pids, status_list=process_result_statuses)


    def is_success(self, pids=[]):
        """
        is_success(pids)

        Waits for a process to end and check if it status is 'success'

        :Parameters:
        * *pids* (`list`) -- list of processes to wait to finish

        """
        return self._status_ok('success', pids)


    def is_failure(self, pids):
        """
        is_failure(pids)

        Waits for a process to end and check if it status is 'failure'

        :Parameters:
        * *pids* (`list`) -- list of processes to wait to finish

        """
        return self._status_ok('failure', pids)


    def is_error(self, pids):
        """
        is_error(pids)

        Waits for a process to end and check if it status is 'error'

        :Parameters:
        * *pids* (`list`) -- list of processes to wait to finish
        """
        return self._status_ok('error', pids)


    def is_timeout(self, pids):
        """
        is_timeout(pids)

        Waits for a process to end and check if it status is 'timeout'

        :Parameters:
        * *pids* (`list`) -- list of processes to wait to finish
        """
        return self._status_ok('timeout', pids)


    def is_warning(self, pids):
        """
        is_warning(pids)

        Waits for a process to end and check if it status is 'warning'

        :Parameters:
        * *pids* (`list`) -- list of processes to wait to finish
        """
        return self._status_ok('warning', pids)


    def is_terminated(self, pids):
        """
        is_terminated(pids)

        Waits for a process to end and check if it status is 'terminated'

        :Parameters:
        * *pids* (`list`) -- list of processes to wait to finish
        """
        return self._status_ok('terminate', pids)


    @apicall
    def get_process_runtime_cache(self, key, pid=None):
        """
        get_process_runtime_cache(key, pid=None)

        Get a pre-defined run time parameter value

        :Parameters:
        * *key* (`string`) -- Identifier of the runtime cache
        * *pid* (`string`) -- Identifier of an existing process

        """
        value = None
        pid = self._get_pid(pid)
        value = self._call_rest_api('get', '/processes/'+pid+'/cache?key=%s'%key, error='Failed to fetch process runtime cache')
        return value


    
    def set_process_runtime_cache(self, key, value, pid=None):
        """
        set_process_runtime_cache(key, value, pid=None)

        Set a process run time parameter

        :Parameters:
        * *key* (`string`) -- parameter key
        * *key* (`value`) -- parameter value
        * *key* (`pid`) -- optional - Identifier of an existing process

        """
        pid = self._get_pid(pid)
        self._call_rest_api('post', '/processes/'+pid+'/cache', data={'key': key, 'value': value}, error='Failed to modify process runtime cache')


    #### GLOBAL PARAMETERS ####
    @apicall
    def search_globals(self, start=0, limit=100, filter={}, **kwargs):
        """
        search_globals(start=0, limit=100, filter={}, **kwargs)

        Search for global parameters

        :Parameters:
        * *start* (`int`) -- start index to retrieve from. Default is 0
        * *limit* (`int`) -- maximum number of entities to retrieve. Default is 100
        * *filter* (`object`) -- free text search pattern (checks in global parameters data)

        :return: List of search results or empty list

        :Example:
        .. code-block:: python

           filter = {'generic': 'my product param'}
           search_result = opereto_client.search_globals(filter=filter)


        """
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/globals', data=request_data, error='Failed to search globals')


    #### KPI ####
    @apicall
    def search_kpi(self, start=0, limit=100, filter={}, **kwargs):
        """
        search_kpi(start=0, limit=100, filter={}, **kwargs)

        Search KPI

        :Parameters:
        * *start* (`int`) -- start index to retrieve from. Default is 0
        * *limit* (`int`) -- maximum number of entities to retrieve. Default is 100
        * *filter* (`object`) -- free text search pattern (checks in kpi data)

        :return: List of search results or empty list

        :Example:
        .. code-block:: python

           filter = {'generic': 'my kpi param'}
           search_result = opereto_client.search_kpi(filter=filter)

        """
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/kpi', data=request_data, error='Failed to search kpi entries')


    
    def modify_kpi(self, kpi_id, product_id, measures=[], append=False, feature_id=None, validator={}, **kwargs):
        """
        modify_kpi(kpi_id, product_id, measures=[], append=False, feature_id=None, validator={}, **kwargs)

        Creates a new kpi or modifies existing one.

      :Parameters:
        * *kpi_id* (`string`) -- The KPI identifier (unique per product)
        * *product_id* (`string`) -- The product (release candidate) identifierier
        * *measures* (`list`) -- List of numeric (integers or floats) measures
        * *append* (`boolean`) -- True to append new measures to existing ones for this API. False to override previous measures
        * *feature_id* (`string`) -- Feature identifier to attach this KPI to a given feature (optional)
        * *validator* (`object`) -- a map of treshhold constains for this measure. The following keys are allowed: gt, gte, lt, lte (optional)

        :Example:
        .. code-block:: python

           # average meature value must be grater or equal to 0 and less or equal to 10.0
           validator = {'gte': 0, 'lte': 10.0}

           client.modify_kpi('general_latency', client.input['opereto_product_id'], measures=[2.2], append=False, feature_id=None, validator=validator)

        """
        if not isinstance(measures, list):
            measures = [measures]
        request_data = {'kpi_id': kpi_id, 'product_id': product_id, 'measures': measures, 'append': append, 'feature_id': feature_id}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/kpi', data=request_data, error='Failed to modify a kpi entry')


    
    def delete_kpi(self, kpi_id, product_id):
        """
        delete_kpi(kpi_id, product_id)

        Delete a key performance indicator (KPI)

      :Parameters:
      * *kpi_id* (`string`) -- The KPI identifier (unique per product)

        """
        return self._call_rest_api('delete', '/kpi/'+kpi_id+'/'+product_id, error='Failed to delete kpi')


    @apicall
    def get_kpi(self, kpi_id, product_id):
        """
        get_kpi(kpi_id, product_id)

        Get KPI information

      :Parameters:
      * *kpi_id* (`string`) -- The KPI identifier (unique per product)
      * *product_id* (`string`) -- The product identifier

      """
        return self._call_rest_api('get', '/kpi/'+kpi_id+'/'+product_id, error='Failed to get kpi information')


    #### TESTS ####
    @apicall
    def search_tests(self, start=0, limit=100, filter={}):
        """
        search_tests(start=0, limit=100, filter={})

        Search tests

        :Parameters:
        * *start* (`int`) -- start index to retrieve from. Default is 0
        * *limit* (`int`) -- maximum number of entities to retrieve. Default is 100
        * *filter* (`object`) -- free text search pattern (checks in tests data)

        :return: List of search results or empty list

        :Example:
        .. code-block:: python

           filter = {'generic': 'my test param'}
           search_result = opereto_client.search_tests(filter=filter)

        """
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        return self._call_rest_api('post', '/search/tests', data=request_data, error='Failed to search tests')




    #### Features ####

    @apicall
    def search_features(self, start=0, limit=100, filter={}, **kwargs):
        """
        search_features(start=0, limit=100, filter={}, **kwargs)

        Search Features

        :Parameters:
        * *start* (`int`) -- start index to retrieve from. Default is 0
        * *limit* (`int`) -- maximum number of entities to retrieve. Default is 100
        * *filter* (`object`) -- free text search pattern

        :return: List of search results or empty list

        :Example:
        .. code-block:: python

           filter = {'generic': 'modify database'}
           search_result = opereto_client.search_features(filter=filter)

        """
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/features', data=request_data, error='Failed to search features')


    def create_feature(self, feature_id, product_id, exec_status, feature_data=None, feature_set=[], pid=None, **kwargs):
        """
        create_feature('my_feature', 'my_product', 'succeess', feature_data='', feature_set=['feature1', 'feature2'])

        Creates a new feature entry. Return the new feature entry identifier in database (feature_uuid)

      :Parameters:
        * *feature_id* (`string`) -- The KPI identifier (unique per product)
        * *product_id* (`string`) -- The product (release candidate) identifier
        * *exec_status* (`list`) -- Execution status. Any of the following: 'success', 'failure', 'error', 'timeout', 'terminated', 'warning'
        * *feature_data* (`string`) -- Any text value associated with this feature
        * *feature_set* (`list`) -- list of features associated with above feature id (optional)
        * *pid* (`string`) -- Identifier of an existing process (optional, if not provided, current process id will be used)
        """

        pid = self._get_pid(pid)
        request_data = {'feature_id': feature_id, 'product_id': product_id, 'exec_status': exec_status, 'feature_data': feature_data, 'feature_set':feature_set, 'process_id': pid}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/features', data=request_data, error='Failed to create a new feature entry')


    #### Dimensions ####

    @apicall
    def search_dimensions(self, start=0, limit=100, filter={}, **kwargs):
        """
        search_dimensions(start=0, limit=100, filter={}, **kwargs)

        Search Dimensions

        :Parameters:
        * *start* (`int`) -- start index to retrieve from. Default is 0
        * *limit* (`int`) -- maximum number of entities to retrieve. Default is 100
        * *filter* (`object`) -- free text search pattern

        :return: List of search results or empty list

        :Example:
        .. code-block:: python

           filter = {'generic': 'my dimention'}
           search_result = opereto_client.search_dimensions(filter=filter)

        """
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/dimensions', data=request_data, error='Failed to search dimensions')


    def modify_dimension(self, dimension_id, name=None, description=None, dimention_tree={}, **kwargs):
        """
        modify_dimension(dimension_id, name=None, description=None, dimention_tree={}, **kwargs)

        Create a new dimension

        :Parameters:

        * *dimension_id* (`string`) -- The dimension identifier
        * *name* (`string`) -- dimension display name (optional)
        * *description* (`string`) -- dimension description (optional)
        * *dimention_tree* (`object`) -- A json representing the dimention features tree

        :return: id of the created feature

        """

        request_data = {'id': dimension_id, 'name': name, 'description': description, 'tree': dimention_tree}
        request_data.update(**kwargs)
        return self._call_rest_api('post', '/dimensions', data=request_data, error='Failed to create a new dimension')


    def delete_dimension(self, dimension_id):
        """
        delete_dimension(dimension_id)

        Delete a dimension

        :Parameters:
        * *dimension_id* (`string`) -- The dimension identifier

        """
        return self._call_rest_api('delete', '/dimensions/' + dimension_id, error='Failed to delete a dimension')

    @apicall
    def get_dimension(self, dimension_id):
        """
        get_dimension(dimension_id)

        Get a given dimension information

        :Parameters:
        * *dimension_id* (`string`) -- The dimension identifier

        """
        return self._call_rest_api('get', '/dimensions/' + dimension_id, error='Failed to get dimension information')



    #### TESTS ####
    @apicall
    def search_tests(self, start=0, limit=100, filter={}):
        """
        search_tests(start=0, limit=100, filter={})

        Search tests

        :Parameters:
        * *start* (`int`) -- start index to retrieve from. Default is 0
        * *limit* (`int`) -- maximum number of entities to retrieve. Default is 100
        * *filter* (`object`) -- free text search pattern (checks in tests data)

        :return: List of search results or empty list

        :Example:
        .. code-block:: python

           filter = {'generic': 'my test param'}
           search_result = opereto_client.search_tests(filter=filter)

        """
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        return self._call_rest_api('post', '/search/tests', data=request_data, error='Failed to search tests')



    @apicall
    def get_test(self, test_id):
        """
        get_test(test_id)

        Get test information.

        :Parameters:
        * *test_id* (`string`) -- The Test identifier

        """
        return self._call_rest_api('get', '/tests/'+test_id, error='Failed to get test information')


    #### QUALITY CRITERIA ####
    @apicall
    def search_qc(self, start=0, limit=100, filter={}):
        """
        search_qc(start=0, limit=100, filter={})

        Search Quality criteria

        :Parameters:
        * *start* (`int`) -- start index to retrieve from. Default is 0
        * *limit* (`int`) -- maximum number of entities to retrieve. Default is 100
        * *filter* (`object`) -- free text search pattern (checks in QC data)

        :return: List of search results or empty list

        :Example:
        .. code-block:: python

           filter = {'generic': 'my qc'}
           search_result = opereto_client.search_qc(filter=filter)
        """
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        return self._call_rest_api('post', '/search/qc', data=request_data, error='Failed to search quality criteria')

    @apicall
    def get_qc(self, qc_id):
        """
        get_qc(qc_id)

        Get criteria information.

        :Parameters:
        * *qc_id* (`string`) -- The QC identifier

        """
        return self._call_rest_api('get', '/qc/'+qc_id, error='Failed to get test information')

    @apicall
    def create_qc(self, product_id=None, expected_result='', actual_result='', weight=100, status='success', **kwargs):
        """
        create_qc(product_id=None, expected_result='', actual_result='', weight=100, status='success', **kwargs)

        Create Quality Criteria

        :Parameters:
        * *product_id* (`string`) -- The product (release candidate) identifier
        * *expected_result* (`string`) -- Text describing the expected result of this criteria
        * *actual_result* (`string`) --  Text describing the actual result of this criteria
        * *weight* (`integer`) -- Overall weight of this criteria (integer between 0-100)
        * *status* (`string`) -- pass/fail/norun

        """
        request_data = {'product_id': product_id, 'expected': expected_result, 'actual': actual_result,'weight': weight, 'exec_status': status}
        request_data.update(**kwargs)
        return self._call_rest_api('post', '/qc', data=request_data, error='Failed to create criteria')

    
    def modify_qc(self, qc_id=None, **kwargs):
        """
        modify_qc(qc_id=None, **kwargs)

        Modify a Quality Criteria

        :Parameters:
        * *qc_id* (`string`) -- The Quality criteria identifier

        """
        if qc_id:
            request_data = {'id': qc_id}
            request_data.update(**kwargs)
            return self._call_rest_api('post', '/qc', data=request_data, error='Failed to modify criteria')
        else:
            return self.create_qc(**kwargs)


    
    def delete_qc(self, qc_id):
        """
        delete_qc(qc_id)

        Delete a quality criteria.

        :Parameters:
        * *qc_id* (`string`) -- The Quality criteria identifier

        """
        return self._call_rest_api('delete', '/qc/'+qc_id, error='Failed to delete criteria')



    #### USERS ####
    @apicall
    def search_users(self, start=0, limit=100, filter={}):
        """
        search_users(start=0, limit=100, filter={})

        Search users

        :Parameters:
        * *start* (`int`) -- start index to retrieve from. Default is 0
        * *limit* (`int`) -- maximum number of entities to retrieve. Default is 100
        * *filter* (`object`) -- free text search pattern (checks in Users data)

        :return: List of search results or empty list

        :Example:
        .. code-block:: python

           filter = {'generic': 'my user'}
           search_result = opereto_client.search_users(filter=filter)

        """
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        return self._call_rest_api('post', '/search/users', data=request_data, error='Failed to search users')


    def upload_datastore(self, pid, datastore_id, zip_file, **kwargs):

        file_size = os.stat(zip_file).st_size
        files = {'service_file': open(zip_file,'rb')}
        url_suffix = '/processes/{}/datastore/{}'.format(pid,datastore_id)

        def my_callback(monitor):
            read_bytes = monitor.bytes_read
            percentage = int(float(read_bytes)/float(file_size)*100)
            if percentage>95:
                percentage=95

            sys.stdout.write('\r{}% Uploaded out of {} Bytes'.format(percentage, file_size))
            sys.stdout.flush()

        e = MultipartEncoder(
            fields=files
        )
        m = MultipartEncoderMonitor(e, my_callback)
        self._connect()
        r  = self.session.post(self.input['opereto_host']+url_suffix, verify=False, data=m)
        sys.stdout.write('\r100% Uploaded out of {} Bytes\n'.format(file_size))
        sys.stdout.flush()
        return self._process_response(r)
