import os,sys
import requests
import json
import yaml
import time
from functools import wraps as _wraps


try:
    from urllib.request import urlopen
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse
    from urllib import urlopen

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

process_result_statuses = ['success', 'failure', 'error', 'timeout', 'terminated', 'warning']
process_running_statuses = ['in_process', 'registered']
process_statuses = process_result_statuses + process_running_statuses


class OperetoClientError(Exception):
    def __init__(self, message, code=500):
        self.message = message
        self.code = code
    def __str__(self):
        return self.message


def apicall(f):

    @_wraps (f)
    def f_call(*args, **kwargs):
        tries=3
        delay=3
        try:
            while tries > 0:
                tries -= 1
                try:
                    rv = f(*args, **kwargs)
                    return rv
                except OperetoClientError as e:
                    try:
                        if e.code>=502:
                            time.sleep(delay)
                        else:
                            raise e
                    except:
                        raise e
                except requests.exceptions.RequestException:
                    time.sleep(delay)
        except Exception as e:
            raise OperetoClientError(str(e))
    return f_call


class OperetoClient(object):

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
                        self.input = yaml.load(f.read())
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

        if self.input.get('opereto_debug'):
            logging.getLogger('OperetoDriver').setLevel(logging.DEBUG)

        ## connect to opereto center
        self.session = None
        self._connect()


    def __del__(self):
        self._disconnect()


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
            response = self.session.post('%s/login'%self.input['opereto_host'], verify=False)
            if response.status_code>201:
                try:
                    error_message = response.json()['message']
                except:
                    error_message=response.reason
                raise OperetoClientError('Failed to login to opereto server [%s]: %s'%(self.input['opereto_host'], error_message))


    def _disconnect(self):
        if self.session:
            self.session.get(self.input['opereto_host']+'/logout', verify=False)


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
            elif response_json.get('data'):
                return response_json['data']


    #### GENERAL ####
    @apicall
    def hello(self):
        '''
        hello(self)

        | Checks if Opereto Server is up and running.

        :Example:
        .. code-block:: python

           opereto_client = OperetoClient()
           opereto_client.hello()
        '''
        return self._call_rest_api('get', '/hello', error='Failed to get response from the opereto server')


    #### MICROSERVICES & VERSIONS ####
    @apicall
    def search_services(self, start=0, limit=100, filter={}, **kwargs):
        '''
        search_services(self, start=0, limit=100, filter={}, **kwargs)

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

        '''
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/services', data=request_data, error='Failed to search services')


    @apicall
    def get_service(self, service_id):
        '''
        get_service(self, service_id)

        | Get a service meta data (id, audit log, type, etc.) information.
        :param string service_id: Identifier of an existing service
        :return: Service meta data

        '''
        return self._call_rest_api('get', '/services/'+service_id, error='Failed to fetch service information')

    @apicall
    def get_service_version(self, service_id, mode='production', version='default'):
        '''
        get_service_version(self, service_id, mode='production', version='default')

        | Get a specific version details of a given service.

        :param string service_id: Identifier of an existing version
        :param string mode: development
        :param string version: default or the version of the service
        :return: json service version details

        '''
        return self._call_rest_api('get', '/services/'+service_id+'/'+mode+'/'+version, error='Failed to fetch service information')

    @apicall
    def verify_service(self, service_id, specification=None, description=None, agent_mapping=None):
        '''
        verify_service(self, service_id, specification=None, description=None, agent_mapping=None)

        | Verifies validity of service yaml

        :param string service_id: Service identification
        :param string specification: service specification yaml
        :param string description: service description written in text or markdown style
        :param string agent_mapping: agents mapping specification
        :return: Object with "success" status or "failure" with specified errors
        :rtype: json

        '''
        request_data = {'id': service_id}
        if specification:
            request_data['spec']=specification
        if description:
            request_data['description']=description
        if agent_mapping:
            request_data['agents']=agent_mapping
        return self._call_rest_api('post', '/services/verify', data=request_data, error='Service [%s] verification failed'%service_id)


    @apicall
    def modify_service(self, service_id, type):
        '''
        modify_service(self, service_id, type)

        :param string service_id: Service identification
        :param type:
        :return:
        '''
        request_data = {'id': service_id, 'type': type}
        return self._call_rest_api('post', '/services', data=request_data, error='Failed to modify service [%s]'%service_id)


    @apicall
    def upload_service_version(self, service_zip_file, mode='production', service_version='default', service_id=None, **kwargs):
        '''
        upload_service_version(self, service_zip_file, mode='production', service_version='default', service_id=None, **kwargs)

        Upload service version

        :param string service_zip_file: zip file location containing service and service specification
        :param enum mode: production/development
        :param string service_version: e.g: 1.0.0
        :param string service_id: service identifier
        :param kwargs:
        :return: success/failure

        '''
        files = {'service_file': open(service_zip_file,'rb')}
        url_suffix = '/services/upload/%s'%mode
        if mode=='production':
            url_suffix+='/'+service_version
        if service_id:
            url_suffix+='/'+service_id
        if kwargs:
            url_suffix=url_suffix+'?'+urlparse.urlencode(kwargs)
        return self._call_rest_api('post', url_suffix, files=files, error='Failed to upload service version')


    @apicall
    def import_service_version(self, repository_json, mode='production', service_version='default', service_id=None, **kwargs):
        '''
        import_service_version(self, repository_json, mode='production', service_version='default', service_id=None, **kwargs)

        Imports a service into Opereto from remote repository

        :param repository_json: Specified the remote repository (+credentials) to import the service zip file from
        :param enum mode: production/development
        :param string service_version:
        :param string service_id:
        :param kwargs:
        :return: success/failure

        '''
        request_data = {'repository': repository_json, 'mode': mode, 'service_version': service_version, 'id': service_id}
        url_suffix = '/services'
        if kwargs:
            url_suffix=url_suffix+'?'+urlparse.urlencode(kwargs)
        return self._call_rest_api('post', url_suffix, data=request_data, error='Failed to import service')

    @apicall
    def delete_service(self, service_id):
        '''
        delete_service(self, service_id)

        Deletes a Service from Opereto

        :param service_id: Service identifier
        :return: success/failure

        '''
        return self._call_rest_api('delete', '/services/'+service_id, error='Failed to delete service')


    @apicall
    def delete_service_version(self, service_id , service_version='default', mode='production'):
        '''
        delete_service(self, service_id)

        Deletes a Service from Opereto

        :param service_id: Service identifier
        :return: success/failure

        '''
        return self._call_rest_api('delete', '/services/'+service_id+'/'+mode+'/'+service_version, error='Failed to delete service')


    @apicall
    def list_development_sandbox(self):
        '''
        list_development_sandbox(self)

        List all services in the current user's development sandbox
        :return: List of sandbox services

        '''
        return self._call_rest_api('get', '/services/sandbox', error='Failed to list sandbox services')


    @apicall
    def purge_development_sandbox(self):
        '''
        purge_development_sandbox(self)

        Purge development sandbox - deletes all services from the current user's development sandbox.

        :return: success/failure

        '''
        return self._call_rest_api('delete', '/services/sandbox', error='Failed to delete sandbox services')


    #### ENVIRONMENTS ####
    @apicall
    def search_environments(self):
        '''
        search_environments(self)

        Get all environments

        :return: List of environments

        '''
        return self._call_rest_api('get', '/search/environments', error='Failed to search environments')

    @apicall
    def get_environment(self, environment_id):
        '''
        get_environment(self, environment_id)

        Get environment general info.


        :param String environment_id: Identifier of an existing environment
        :return: environment data

        '''
        return self._call_rest_api('get', '/environments/'+environment_id, error='Failed to fetch environment [%s]'%environment_id)

    @apicall
    def verify_environment_scheme(self, environment_type, environment_topology):
        '''
        verify_environment_scheme(self, environment_type, environment_topology)

        Verify environment scheme

        :param string environment_type:
        :param string environment_topology:
        '''
        request_data = {'type': environment_type, 'topology': environment_topology}
        return self._call_rest_api('post', '/environments/verify', data=request_data, error='Failed to verify environment.')

    @apicall
    def verify_environment(self, environment_id):
        '''
        verify_environment(self, environment_id)

        :param environment_id: environment identifier
        '''
        request_data = {'id': environment_id}
        return self._call_rest_api('post', '/environments/verify', data=request_data, error='Failed to verify environment.')

    @apicall
    def create_environment(self, topology_name, topology={}, id=None, **kwargs):
        '''
        create_environment(self, topology_name, topology={}, id=None, **kwargs)

        Create a new environment.
        :param string topology_name: The topology identifier. Must be provided to create an environment.
        :param topology: Topology data (must match the topology json schema)
        :param id: The environment identifier. If none provided when creating environment, Opereto will automatically assign a unique identifier.
        :param kwargs:
        :return: success and id of created environment

        '''
        request_data = {'topology_name': topology_name,'id': id, 'topology':topology, 'add_only':True}
        request_data.update(**kwargs)
        return self._call_rest_api('post', '/environments', data=request_data, error='Failed to create environment')

    @apicall
    def modify_environment(self, environment_id, **kwargs):
        '''
        modify_environment(self, environment_id, **kwargs)

        Modifies an existing environment

        :param string environment_id: The environment identifier.
        :param kwargs: variables to change in the environment
        :return: success/failure

        '''
        request_data = {'id': environment_id}
        request_data.update(**kwargs)
        return self._call_rest_api('post', '/environments', data=request_data, error='Failed to modify environment')

    @apicall
    def delete_environment(self, environment_id):
        '''
        delete_environment(self, environment_id)

        Delete an existing environment

        :param string environment_id: Identifier of an existing environment
        :return: success/failure

        '''
        return self._call_rest_api('delete', '/environments/'+environment_id, error='Failed to delete environment [%s]'%environment_id)


    #### AGENTS ####
    @apicall
    def search_agents(self, start=0, limit=100, filter={}, **kwargs):
        '''
        search_agents(self, start=0, limit=100, filter={}, **kwargs)

        Search agents
        :param int start: start index to retrieve from
        :param int limit: Maximum number of entities to retrieve
        :param json filter: filters the search query with Free text search pattern
             example:
             {
                "filter":
                {
                    "generic":"My agent"
                }
             }
        :param kwargs:
        :return: List of found agents
        '''
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/agents', data=request_data, error='Failed to search agents')

    @apicall
    def get_agents(self, agent_id):
        '''
        get_agents(self, agent_id)

        Get agent general details

        :param string agent_id: Identifier of an existing agent
        :return: Agent general details
        '''
        return self._call_rest_api('get', '/agents/'+agent_id, error='Failed to fetch agent details.')


    @apicall
    def get_agent_properties(self, agent_id):
        '''
        get_agent_properties(self, agent_id)

        Get agent properties separated to custom properties defined by the user and built-in properties provided by Opereto.

        :param string agent_id: Identifier of an existing agent
        :return: agent properties json
        '''
        return self._call_rest_api('get', '/agents/'+agent_id+'/properties', error='Failed to fetch agent [%s] properties'%agent_id)

    @apicall
    def get_all_agents(self):
        '''
        get_all_agents(self)

        Get all agents

        :return: list of existing agents

        '''
        return self._call_rest_api('get', '/agents/all', error='Failed to fetch agents')


    @apicall
    def modify_agent_property(self, agent_id, key, value):
        '''
        modify_agent_property(self, agent_id, key, value)

        Modifies agent single property.

        :param string agent_id: Identifier of an existing agent
        :param key: key of key-value json map
        :param value: value key-value json map
        :return:success/failure
        '''
        return self._call_rest_api('post', '/agents/'+agent_id+'/properties', data={key: value}, error='Failed to modify agent [%s] property [%s]'%(agent_id,key))


    @apicall
    def modify_agent_properties(self, agent_id, key_value_map={}):
        '''
        modify_agent_properties(self, agent_id, key_value_map={})

        Modify agent properties

        :param string agent_id: Identifier of an existing agent
        :param json key_value_map: key value map of properties to change
               example:
               {
                 "mykey": "myvalue",
                 "mykey2": "myvalue2"
                }
        :return: success/failure
        '''
        return self._call_rest_api('post', '/agents/'+agent_id+'/properties', data=key_value_map, error='Failed to modify agent [%s] properties'%agent_id)


    @apicall
    def create_agent(self, agent_id=None, **kwargs):
        '''
        create_agent(self, agent_id=None, **kwargs)

        | Creates an agent based on the identifier provided.
        | The agent will become online when a real agent will connect using this identifier.
        | However, in most cases, the agent entity is created automatically when a new agent connects to opereto.

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


        '''

        request_data = {'id': agent_id, 'add_only':True}
        request_data.update(**kwargs)
        return self._call_rest_api('post', '/agents'+'', data=request_data, error='Failed to create agent')


    @apicall
    def modify_agent(self, agent_id, **kwargs):
        '''
        modify_agent(self, agent_id, **kwargs)

        | Modifies agent information.

        :param string agent_id: Identifier of an existing agent
        :param kwargs: agent properties to change
        :return:success/failure
        '''
        request_data = {'id': agent_id}
        request_data.update(**kwargs)
        return self._call_rest_api('post', '/agents'+'', data=request_data, error='Failed to modify agent [%s]'%agent_id)


    @apicall
    def get_agent(self, agent_id):
        '''
        get_agent(self, agent_id)

        Get agent general details

        :param string agent_id: Identifier of an existing agent
        :return: agent, e.g: {
          "status": "success",
          "data": {
            "active": true,
            "modified_date": "2015-10-31T18:48:08.309566",
            "id": "my_agent",
            "online": false
          }
        }

        '''
        return self._call_rest_api('get', '/agents/'+agent_id, error='Failed to fetch agent [%s] status'%agent_id)

    @apicall
    def get_agent_status(self, agent_id):
        '''
        get_agent_status(self, agent_id)

        Get agent status

        :param string agent_id: Identifier of an existing agent
        :return: See get_agent
        '''
        return self.get_agent(agent_id)

    @apicall
    def delete_agent(self, agent_id):
        return self._call_rest_api('delete', '/agents/'+agent_id, error='Failed to delete agent [%s] status'%agent_id)

    #### PROCESSES ####
    @apicall
    def create_process(self, service, agent=None, title=None, mode=None, service_version=None, **kwargs):
        '''
        create_process(self, service, agent=None, title=None, mode=None, service_version=None, **kwargs)

        Registers a new process

        :param string service: service name
        :param string agent: a valid value may be one of the following: agent identifier, agent identifiers (list) : ["agent_1", "agent_2"..], "all", "any"
        :param string title: title
        :param enum mode: production/development
        :param string service_version:
        :param kwargs: process attributes
        :return: success/failure and process id

        '''
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
        else:
            message += ' [agent = any ]'
        self.logger.info(message)
        return str(pid)


    @apicall
    def rerun_process(self, pid, title=None, agent=None):
        '''
        rerun_process(self, pid, title=None, agent=None)

        Rerun process

        :param string pid: Process ID to rerun
        :param string title: title for the new Process
        :param string agent: a valid value may be one of the following: agent identifier, agent identifiers (list) : ["agent_1", "agent_2"..], "all", "any"
        :return: success/failure and process id
        '''
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


    @apicall
    def modify_process_properties(self, key_value_map={}, pid=None):
        '''
        modify_process_properties(self, key_value_map={}, pid=None)

        Modify process output properties.
        Please note that process property key provided must be declared as an output property in the relevant service specification.

        :param json key value map key_value_map: key value map with process properties to modify
        :param string pid: Identifier of an existing process
        :return: success/failure

        '''
        pid = self._get_pid(pid)
        request_data={"properties": key_value_map}
        return self._call_rest_api('post', '/processes/'+pid+'/output', data=request_data, error='Failed to output properties')

    @apicall
    def modify_process_property(self, key, value, pid=None):
        '''
        modify_process_property(self, key, value, pid=None)

        Modify process output property.
        Please note that the process property key provided must be declared as an output property in the relevant service specification.

        :param string key: key of property to modify
        :param string value: value of property to modify
        :param string pid: Process identifier
        :return: success/failure
        '''
        pid = self._get_pid(pid)
        request_data={"key" : key, "value": value}
        return self._call_rest_api('post', '/processes/'+pid+'/output', data=request_data, error='Failed to modify output property [%s]'%key)

    @apicall
    def modify_process_summary(self, pid=None, text=''):
        '''
        modify_process_summary(self, pid=None, text='')

        :param string pid: Identifier of an existing process
        :param string text: new summary text to update
        :return: success/failure

        '''
        pid = self._get_pid(pid)
        request_data={"id" : pid, "data": str(text)}
        return self._call_rest_api('post', '/processes/'+pid+'/summary', data=request_data, error='Failed to update process summary')


    @apicall
    def stop_process(self, pids, status='success'):
        '''
        stop_process(self, pids, status='success')

        :param string pids: Identifier of an existing process
        :param string status: Any of the following possible values:  success , failure , error , warning , terminated
        :return: success/failure
        '''
        if status not in process_result_statuses:
            raise OperetoClientError('Invalid process result [%s]'%status)
        pids = self._get_pids(pids)
        for pid in pids:
            self._call_rest_api('post', '/processes/'+pid+'/terminate/'+status, error='Failed to stop process')


    @apicall
    def get_process_status(self, pid=None):
        '''
        get_process_status(self, pid=None)

        Get status of a process

        :param string pid: Process Identifier
        :return:
        '''
        pid = self._get_pid(pid)
        return self._call_rest_api('get', '/processes/'+pid+'/status', error='Failed to fetch process status')


    @apicall
    def get_process_flow(self, pid=None):
        '''
        get_process_flow(self, pid=None)

        Get process in flow context.

        :param string pid: Process identifier
        :return: process flow
        '''
        pid = self._get_pid(pid)
        return self._call_rest_api('get', '/processes/'+pid+'/flow', error='Failed to fetch process information')


    @apicall
    def get_process_rca(self, pid=None):
        '''
        get_process_rca(self, pid=None)

        Get the RCA tree of a given failed process. The RCA tree contains all failed child processes that caused the failure of the given process.

        :param string pid: Process Identifier
        :return: failed child processes that caused the failure of the given process.
        '''
        pid = self._get_pid(pid)
        return self._call_rest_api('get', '/processes/'+pid+'/rca', error='Failed to fetch process information')


    @apicall
    def get_process_info(self, pid=None):
        '''
        get_process_info(self, pid=None)

        Get information of a given process

        :param string pid: Process Identifier
        :return: Process general information
        '''

        pid = self._get_pid(pid)
        return self._call_rest_api('get', '/processes/'+pid, error='Failed to fetch process information')

    @apicall
    def get_process_log(self, pid=None, start=0, limit=1000):
        '''
        get_process_log(self, pid=None, start=0, limit=1000

        :param string pid: Process Identifier
        :param int start: start index to retrieve from
        :param int limit: Maximum number of entities to retrieve
        :return: List of process log entries
        '''
        pid = self._get_pid(pid)
        data = self._call_rest_api('get', '/processes/'+pid+'/log?start={}&limit={}'.format(start,limit), error='Failed to fetch process log')
        return data['list']


    ## deprecated
    def get_process_property(self, pid=None, name=None):
        pid = self._get_pid(pid)
        return self.get_process_properties(pid, name)


    @apicall
    def get_process_properties(self, pid=None, name=None):
        '''
        get_process_properties(self, pid=None, name=None)

        Get process properties (both input and output properties)

        :param string pid: Process Identifier
        :param string name: optional - Property name
        :return: Properties of a process
        '''
        pid = self._get_pid(pid)
        res = self._call_rest_api('get', '/processes/'+pid+'/properties', error='Failed to fetch process properties')
        if name:
            try:
                return res[name]
            except KeyError as e:
                raise OperetoClientError(message='Invalid property [%s]'%name, code=404)
        else:
            return res


    @apicall
    def wait_for(self, pids=[], status_list=process_result_statuses):
        '''
        wait_for(self, pids=[], status_list=process_result_statuses)

        :param pids: list of processes to be in the given status list or to finish
        :param status_list: optional - statuses to wait for.
        :return: statuses of finished process
        '''
        results={}
        pids = self._get_pids(pids)
        for pid in pids:
            while(True):
                try:
                    stat = self._call_rest_api('get', '/processes/'+pid+'/status', error='Failed to fetch process [%s] status'%pid)
                    if stat in status_list:
                        results[pid]=stat
                        break
                    time.sleep(5)
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
        '''
        wait_to_start(self, pids=[])

        Wait for a process to start

        :param pids: list of processes to wait to start
        :return: status of finished process
        '''
        actual_pids = self._get_pids(pids)
        return self.wait_for(pids=actual_pids, status_list=process_result_statuses+['in_process'])


    def wait_to_end(self, pids=[]):
        '''
        wait_to_end(self, pids=[])

        Wait for a process to end

        :param pids: list of processes to wait to finish
        :return: status of finished process

        '''
        actual_pids = self._get_pids(pids)
        return self.wait_for(pids=actual_pids, status_list=process_result_statuses)


    def wait_to_end(self, pids=[]):
        '''
        wait_to_end(self, pids=[])

        :param pids:
        :return: status of finished process
        '''
        return self._status_ok('success', pids)


    def is_failure(self, pids):
        '''
        is_failure(self, pids)

        :param pids:
        :return:
        '''
        return self._status_ok('failure', pids)


    def is_error(self, pids):
        '''
        is_error(self, pids)

        :param pids:
        :return:
        '''
        return self._status_ok('error', pids)


    def is_timeout(self, pids):
        '''
        is_timeout(self, pids)

        :param pids:
        :return:
        '''
        return self._status_ok('timeout', pids)


    def is_warning(self, pids):
        '''
        is_warning(self, pids)

        :param pids:
        :return:
        '''
        return self._status_ok('warning', pids)


    def is_terminated(self, pids):
        '''
        is_terminated(self, pids)

        :param pids:
        :return:
        '''
        return self._status_ok('terminate', pids)


    @apicall
    def get_process_runtime_cache(self, key, pid=None):
        '''
        get_process_runtime_cache(self, key, pid=None)

        Get a pre-defined run time parameter value

        :param key: Identifier of the runtime cache
        :param pid: Identifier of an existing process
        :return: pre-defined runtime parameter value
        '''
        value = None
        pid = self._get_pid(pid)
        value = self._call_rest_api('get', '/processes/'+pid+'/cache?key=%s'%key, error='Failed to fetch process runtime cache')
        return value


    @apicall
    def set_process_runtime_cache(self, key, value, pid=None):
        '''
        set_process_runtime_cache(self, key, value, pid=None)

        Set a process run time parameter

        :param string key: parameter key
        :param string value: parameter value
        :param string pid: Identifier of an existing process
        :return:
        '''
        pid = self._get_pid(pid)
        self._call_rest_api('post', '/processes/'+pid+'/cache', data={'key': key, 'value': value}, error='Failed to modify process runtime cache')


    #### GLOBAL PARAMETERS ####
    @apicall
    def search_globals(self, start=0, limit=100, filter={}, **kwargs):
        '''
        search_globals(self, start=0, limit=100, filter={}, **kwargs)

        Search for global parameters

        :param int start: start index to retrieve from
        :param int limit: Limit the number of responses
        :param json filter: filters the search query with Free text search pattern
             example:
             {
                "filter":
                {
                    "generic":"my global param"
                }
             }
        :param kwargs:
        :return: Found Globals
        '''
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/globals', data=request_data, error='Failed to search globals')

    #### PRODUCTS ####

    @apicall
    def search_products(self, start=0, limit=100, filter={}, **kwargs):
        '''
        search_products(self, start=0, limit=100, filter={}, **kwargs)

        :param int start: start index to retrieve from
        :param int limit: Limit the number of responses
        :param json filter: filters the search query with Free text search pattern
             example:
             {
                "filter":
                {
                    "generic":"my product param"
                }
             }
        :param kwargs:
        :return: Found Products
        '''
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/products', data=request_data, error='Failed to search products')

    @apicall
    def create_product(self, product, version, build, name=None, description=None, attributes={}):
        '''
        create_product(self, product, version, build, name=None, description=None, attributes={})

        Create product

        :param product:
        :param version:
        :param build:
        :param name:
        :param description:
        :param attributes:
        :return: success/failure
        '''
        request_data = {'product': product, 'version': version, 'build': build}
        if name: request_data['name']=name
        if description: request_data['description']=description
        if attributes: request_data['attributes']=attributes
        ret_data= self._call_rest_api('post', '/products', data=request_data, error='Failed to create a new product')
        pid = ret_data
        message = 'New product created [pid = %s] '%pid
        self.logger.info(message)
        return str(pid)


    @apicall
    def modify_product(self, product_id, name=None, description=None, attributes={}):
        '''
        modify_product(self, product_id, name=None, description=None, attributes={})

        Modify product

        :param product_id:
        :param name:
        :param description:
        :param attributes:
        :return: success/failure
        '''
        request_data = {'id': product_id}
        if name: request_data['name']=name
        if description: request_data['description']=description
        if attributes: request_data['attributes']=attributes
        return self._call_rest_api('post', '/products', data=request_data, error='Failed to modify a new product')


    @apicall
    def delete_product(self, product_id):
        '''
        delete_product(self, product_id)

        Delete a product

        :param product_id:
        :return: success/failure
        '''
        return self._call_rest_api('delete', '/products/'+product_id, error='Failed to delete product')


    @apicall
    def get_product(self, product_id):
        '''
        get_product(self, product_id)

        Get an existing product information

        :param product_id: Identifier of an existing product
        :return: Product information
        '''
        return self._call_rest_api('get', '/products/'+product_id, error='Failed to get product information')


    #### KPI ####
    @apicall
    def search_kpi(self, start=0, limit=100, filter={}, **kwargs):
        '''
        search_kpi(self, start=0, limit=100, filter={}, **kwargs)

        Search KPI

        :param int start: start index to retrieve from
        :param int limit: Limit the number of responses
        :param json filter: filters the search query with Free text search pattern
             example:
             {
                "filter":
                {
                    "generic":"my Kpi"
                }
             }
        :param kwargs:
        :return: KPI
        '''
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/kpi', data=request_data, error='Failed to search kpi entries')


    @apicall
    def modify_kpi(self, kpi_id, product_id, measures=[], append=False, **kwargs):
        '''
        modify_kpi(self, kpi_id, product_id, measures=[], append=False, **kwargs)

        Creates a new kpi or modifies existing one.

        :param string kpi_id: The KPI identifier (unique per product)
        :param string product_id: The product (release candidate) identifier
        :param array measures: List of numeric (integers or floats) measures
        :param boolean append: True to append new measures to existing ones for this API. False to override previous measures.
        :param kwargs:
        :return: KPI
        '''
        if not isinstance(measures, list):
            measures = [measures]
        request_data = {'kpi_id': kpi_id, 'product_id': product_id, 'measures': measures, 'append': append}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/kpi', data=request_data, error='Failed to modify a kpi entry')


    @apicall
    def delete_kpi(self, kpi_id, product_id):
        '''
        delete_kpi(self, kpi_id, product_id)

        Delete a key performance indicator (KPI)

        :param kpi_id:
        :param product_id:
        :return: success/failure
        '''
        return self._call_rest_api('delete', '/kpi/'+kpi_id+'/'+product_id, error='Failed to delete kpi')


    @apicall
    def get_kpi(self, kpi_id, product_id):
        '''
        get_kpi(self, kpi_id, product_id)

        Get KPI information

        :param kpi_id:
        :param product_id:
        :return: KPI
        '''
        return self._call_rest_api('get', '/kpi/'+kpi_id+'/'+product_id, error='Failed to get kpi information')


    #### TESTS ####
    @apicall
    def search_tests(self, start=0, limit=100, filter={}):
        '''
        search_tests(self, start=0, limit=100, filter={})

        Search tests

        :param int start: start index to retrieve from
        :param int limit: Limit the number of responses
        :param json filter: filters the search query with Free text search pattern
             example:
             {
                "filter":
                {
                    "generic":"my Test"
                }
             }
        :return: List of found tests
        '''
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        return self._call_rest_api('post', '/search/tests', data=request_data, error='Failed to search tests')


    @apicall
    def get_test(self, test_id):
        '''
        get_test(self, test_id)

        Get test information.

        :param test_id:
        :return: Test information
        '''
        return self._call_rest_api('get', '/tests/'+test_id, error='Failed to get test information')


    #### QUALITY CRITERIA ####
    @apicall
    def search_qc(self, start=0, limit=100, filter={}):
        '''
        search_qc(self, start=0, limit=100, filter={})

        :param int start: start index to retrieve from
        :param int limit: Limit the number of responses
        :param json filter: filters the search query with Free text search pattern
             example:
             {
                "filter":
                {
                    "generic":"my QC"
                }
             }
        :return: Quality Criteria information
        '''
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        return self._call_rest_api('post', '/search/qc', data=request_data, error='Failed to search quality criteria')

    @apicall
    def get_qc(self, qc_id):
        '''
        get_qc(self, qc_id)

        Get criteria information.

        :param qc_id:
        :return: Quality Criteria
        '''
        return self._call_rest_api('get', '/qc/'+qc_id, error='Failed to get test information')

    @apicall
    def create_qc(self, product_id=None, expected_result='', actual_result='', weight=100, status='success', **kwargs):
        '''
        create_qc(self, product_id=None, expected_result='', actual_result='', weight=100, status='success', **kwargs)

        :param string product_id: The product (release candidate) identifier
        :param string expected_result: Text describing the expected result of this criteria
        :param string actual_result: Text describing the actual result of this criteria
        :param string weight: Overall weight of this criteria (integer between 0-100)
        :param enum status: pass/fail/norun
        :param kwargs:
        :return:success/failure
        '''
        request_data = {'product_id': product_id, 'expected': expected_result, 'actual': actual_result,'weight': weight, 'exec_status': status}
        request_data.update(**kwargs)
        return self._call_rest_api('post', '/qc', data=request_data, error='Failed to create criteria')

    @apicall
    def modify_qc(self, qc_id=None, **kwargs):
        '''
        modify_qc(self, qc_id=None, **kwargs)

        Modify a Quality Criteria

        :param qc_id:
        :param kwargs:
        :return:success/failure
        '''
        if qc_id:
            request_data = {'id': qc_id}
            request_data.update(**kwargs)
            return self._call_rest_api('post', '/qc', data=request_data, error='Failed to modify criteria')
        else:
            return self.create_qc(**kwargs)


    @apicall
    def delete_qc(self, qc_id):
        '''
        delete_qc(self, qc_id)

        Delete quality criteria.

        :param qc_id:
        :return:success/failure
        '''
        return self._call_rest_api('delete', '/qc/'+qc_id, error='Failed to delete criteria')



    #### USERS ####
    @apicall
    def search_users(self, start=0, limit=100, filter={}):
        '''
        search_users(self, start=0, limit=100, filter={})

        Search users

        :param start:
        :param limit:
        :param filter:
        :return: List of users
        '''
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        return self._call_rest_api('post', '/search/users', data=request_data, error='Failed to search users')

