import os,sys
import requests
import json
import yaml
import time
import types


try:
    requests.packages.urllib3.disable_warnings()
except AttributeError:
    pass

import logging
FORMAT = '%(asctime)s: [%(levelname)s] %(message)s'
logging.basicConfig(stream=sys.stdout, format=FORMAT, level=logging.ERROR)
logger = logging.getLogger('OperetoClient')
logging.getLogger("OperetoClient").setLevel(logging.INFO)

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
    def f_call(*args, **kwargs):
        tries=3
        delay=3
        try:
            while tries > 0:
                tries -= 1
                try:
                    rv = f(*args, **kwargs)
                    return rv
                except OperetoClientError,e:
                    try:
                        if e.code>=502:
                            time.sleep(delay)
                        else:
                            raise e
                    except:
                        raise e
                except requests.exceptions.RequestException:
                    time.sleep(delay)
        except Exception,e:
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
            if not os.path.exists(file):
                return False
            try:
                with open(file, 'r') as f:
                    if file.endswith('.json'):
                        self.input = json.loads(f.read())
                    else:
                        self.input = yaml.load(f.read())
            except Exception,e:
                raise OperetoClientError('Failed to parse %s: %s'%(file, str(e)))

        if not get_credentials(os.path.join(work_dir,'arguments.json')):
            if not get_credentials(os.path.join(work_dir,'arguments.yaml')):
                get_credentials(os.path.join(home_dir,'opereto.yaml'))

        ## TEMP: fix in agent
        for item in self.input.keys():
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
        return self._call_rest_api('get', '/hello', error='Failed to get response from the opereto server')


    #### MICROSERVICES & VERSIONS ####
    @apicall
    def search_services(self, start=0, limit=100, filter={}, **kwargs):
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/services', data=request_data, error='Failed to search services')


    @apicall
    def get_service(self, service_id):
        return self._call_rest_api('get', '/services/'+service_id, error='Failed to fetch service information')

    @apicall
    def get_service_version(self, service_id, mode='production', version='default'):
        return self._call_rest_api('get', '/services/'+service_id+'/'+mode+'/'+version, error='Failed to fetch service information')

    @apicall
    def verify_service(self, service_id, specification=None, description=None, agent_mapping=None):
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
        request_data = {'id': service_id, 'type': type}
        return self._call_rest_api('post', '/services', data=request_data, error='Failed to modify service [%s]'%service_id)


    @apicall
    def upload_service_version(self, service_zip_file, mode='production', service_version='default', service_id=None):
        files = {'service_file': open(service_zip_file,'rb')}

        url_suffix = '/services/upload/%s'%mode
        if mode=='production':
            url_suffix+='/'+service_version
            if service_id:
                url_suffix+='/'+service_id
        return self._call_rest_api('post', url_suffix, files=files, error='Failed to upload service version')


    @apicall
    def import_service_version(self, repository_json, mode='production', service_version='default', service_id=None):
        request_data = {'repository': repository_json, 'mode': mode, 'service_version': service_version, 'id': service_id}
        return self._call_rest_api('post', '/services', data=request_data, error='Failed to import service')

    @apicall
    def delete_service(self, service_id):
        return self._call_rest_api('delete', '/services/'+service_id, error='Failed to delete service')


    @apicall
    def delete_service_version(self, service_id , service_version='default', mode='production'):
        return self._call_rest_api('delete', '/services/'+service_id+'/'+mode+'/'+service_version, error='Failed to delete service')


    @apicall
    def list_development_sandbox(self):
        return self._call_rest_api('get', '/services/sandbox', error='Failed to list sandbox services')


    @apicall
    def purge_development_sandbox(self):
        return self._call_rest_api('delete', '/services/sandbox', error='Failed to delete sandbox services')



    #### ENVIRONMENTS ####
    @apicall
    def search_environments(self):
        return self._call_rest_api('get', '/search/environments', error='Failed to search environments')

    @apicall
    def get_environment(self, environment_id):
        return self._call_rest_api('get', '/environments/'+environment_id, error='Failed to fetch environment [%s]'%environment_id)


    @apicall
    def create_environment(self, environment_type, environment_id , agents):
        request_data = {'environment_id': environment_id, 'environment_type': environment_type, 'agents': agents}
        return self._call_rest_api('post', '/environments', data=request_data, error='Failed to create environment [%s]'%environment_id)


    @apicall
    def delete_environment(self, environment_id):
        return self._call_rest_api('delete', '/environments/'+environment_id, error='Failed to delete environment [%s]'%environment_id)


    #### AGENTS ####
    @apicall
    def search_agents(self, start=0, limit=100, filter={}, **kwargs):
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/agents', data=request_data, error='Failed to search agents')

    @apicall
    def get_agents(self, agent_id):
        return self._call_rest_api('get', '/agents/'+agent_id, error='Failed to fetch agent details.')


    @apicall
    def get_agent_properties(self, agent_id):
        return self._call_rest_api('get', '/agents/'+agent_id+'/properties', error='Failed to fetch agent [%s] properties'%agent_id)

    @apicall
    def get_all_agents(self):
        return self._call_rest_api('get', '/agents/all', error='Failed to fetch agents')


    @apicall
    def modify_agent_property(self, agent_id, key, value):
        return self._call_rest_api('post', '/agents/'+agent_id+'/properties', data={key: value}, error='Failed to modify agent [%s] property [%s]'%(agent_id,key))


    @apicall
    def modify_agent_properties(self, agent_id, key_value_map={}):
        return self._call_rest_api('post', '/agents/'+agent_id+'/properties', data=key_value_map, error='Failed to modify agent [%s] properties'%agent_id)


    @apicall
    def get_agent_status(self, agent_id):
        return self._call_rest_api('get', '/agents/'+agent_id, error='Failed to fetch agent [%s] status'%agent_id)

    #### PROCESSES ####
    @apicall
    def create_process(self, service, agent='any', title=None, mode='production', service_version=None, **kwargs):
        request_data = {'service_id': service, 'agents': str(agent), 'mode': mode, 's_version':service_version}
        if title:
            request_data['name']=title

        if self.input.get('pid'):
            request_data['pflow_id']=self.input.get('pid')

        request_data.update(**kwargs)
        ret_data= self._call_rest_api('post', '/processes', data=request_data, error='Failed to create a new process')

        if not isinstance(ret_data, types.ListType):
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
    def modify_process_properties(self, key_value_map={}, pid=None):
        pid = self._get_pid(pid)
        request_data={"properties": key_value_map}
        return self._call_rest_api('post', '/processes/'+pid+'/output', data=request_data, error='Failed to output properties')

    @apicall
    def modify_process_property(self, key, value, pid=None):
        pid = self._get_pid(pid)
        request_data={"key" : key, "value": value}
        return self._call_rest_api('post', '/processes/'+pid+'/output', data=request_data, error='Failed to modify output property [%s]'%key)

    @apicall
    def modify_process_summary(self, pid=None, text=''):
        pid = self._get_pid(pid)
        request_data={"id" : pid, "data": str(text)}
        return self._call_rest_api('post', '/processes/'+pid+'/summary', data=request_data, error='Failed to update process summary')


    @apicall
    def stop_process(self, pids, status='success'):
        if status not in process_result_statuses:
            raise OperetoClientError('Invalid process result [%s]'%status)
        pids = self._get_pids(pids)
        for pid in pids:
            self._call_rest_api('post', '/processes/'+pid+'/terminate/'+status, error='Failed to stop process')


    @apicall
    def get_process_status(self, pid=None):
        pid = self._get_pid(pid)
        return self._call_rest_api('get', '/processes/'+pid+'/status', error='Failed to fetch process status')


    @apicall
    def get_process_flow(self, pid=None):
        pid = self._get_pid(pid)
        return self._call_rest_api('get', '/processes/'+pid+'/flow', error='Failed to fetch process information')


    @apicall
    def get_process_rca(self, pid=None):
        pid = self._get_pid(pid)
        return self._call_rest_api('get', '/processes/'+pid+'/rca', error='Failed to fetch process information')


    @apicall
    def get_process_info(self, pid=None):
        pid = self._get_pid(pid)
        return self._call_rest_api('get', '/processes/'+pid, error='Failed to fetch process information')

    @apicall
    def get_process_log(self, pid=None, start=0, limit=1000):
        pid = self._get_pid(pid)
        return self._call_rest_api('get', '/processes/'+pid+'/log?start={}&limit={}'.format(start,limit), error='Failed to fetch process log')


    ## deprecated
    def get_process_property(self, pid=None, name=None):
        pid = self._get_pid(pid)
        return self.get_process_properties(pid, name)


    @apicall
    def get_process_properties(self, pid=None, name=None):
        pid = self._get_pid(pid)
        res = self._call_rest_api('get', '/processes/'+pid+'/properties', error='Failed to fetch process properties')
        if name:
            try:
                return res[name]
            except KeyError, e:
                raise OperetoClientError(message='Invalid property [%s]'%name, code=404)
        else:
            return res


    @apicall
    def wait_for(self, pids=[], status_list=process_result_statuses):
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
        for pid,stat in statuses.items():
            if stat!=status:
                self.logger.error('But it ended with status [%s]'%stat)
                return False
        return True


    def wait_to_start(self, pids=[]):
        actual_pids = self._get_pids(pids)
        return self.wait_for(pids=actual_pids, status_list=process_result_statuses+['in_process'])


    def wait_to_end(self, pids=[]):
        actual_pids = self._get_pids(pids)
        return self.wait_for(pids=actual_pids, status_list=process_result_statuses)


    def is_success(self, pids):
        return self._status_ok('success', pids)


    def is_failure(self, pids):
        return self._status_ok('failure', pids)


    def is_error(self, pids):
        return self._status_ok('error', pids)


    def is_timeout(self, pids):
        return self._status_ok('timeout', pids)


    def is_warning(self, pids):
        return self._status_ok('warning', pids)


    def is_terminated(self, pids):
        return self._status_ok('terminate', pids)


    @apicall
    def get_process_runtime_cache(self, key, pid=None):
        value = None
        pid = self._get_pid(pid)
        value = self._call_rest_api('get', '/processes/'+pid+'/cache?key=%s'%key, error='Failed to fetch process runtime cache')
        return value


    @apicall
    def set_process_runtime_cache(self, key, value, pid=None):
        pid = self._get_pid(pid)
        self._call_rest_api('post', '/processes/'+pid+'/cache', data={'key': key, 'value': value}, error='Failed to modify process runtime cache')


    #### GLOBAL PARAMETERS ####
    @apicall
    def search_globals(self, start=0, limit=100, filter={}, **kwargs):
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/globals', data=request_data, error='Failed to search globals')

    #### CONTINUOUS TESTING ####
    @apicall
    def search_products(self, start=0, limit=100, filter={}, **kwargs):
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        request_data.update(kwargs)
        return self._call_rest_api('post', '/search/products', data=request_data, error='Failed to search products')

    @apicall
    def create_product(self, product, version, build, name=None, description=None, attributes={}):
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
        request_data = {'id': product_id}
        if name: request_data['name']=name
        if description: request_data['description']=description
        if attributes: request_data['attributes']=attributes
        return self._call_rest_api('post', '/products', data=request_data, error='Failed to modify a new product')


    @apicall
    def delete_product(self, product_id):
        return self._call_rest_api('delete', '/products/'+product_id, error='Failed to delete product')


    @apicall
    def get_product(self, product_id):
        return self._call_rest_api('get', '/products/'+product_id, error='Failed to get product information')


    @apicall
    def search_tests(self, start=0, limit=100, filter={}):
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        return self._call_rest_api('post', '/search/tests', data=request_data, error='Failed to search tests')


    @apicall
    def get_test(self, test_id):
        return self._call_rest_api('get', '/tests/'+test_id, error='Failed to get test information')