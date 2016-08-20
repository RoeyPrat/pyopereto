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
    def __init__(self, message, code=None):
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

        if os.path.exists(os.path.join(work_dir,'arguments.json')):
            try:
                with open(os.path.join(work_dir,'arguments.json'), 'r') as f:
                    self.input = json.loads(f.read())
            except Exception,e:
                raise OperetoClientError('Failed to parse %s input file: %s'%('arguments.json', str(e)))
        elif os.path.exists(os.path.join(work_dir,'arguments.yaml')):
            try:
                with open(os.path.join(work_dir,'arguments.yaml'), 'r') as f:
                    self.input = yaml.load(f.read())
            except Exception,e:
                raise OperetoClientError('Failed to parse %s input file: %s'%('arguments.yaml', str(e)))


        ## TEMP: fix in agent
        for item in self.input.keys():
            try:
                if self.input[item]=='null':
                    self.input[item]=None
                else:
                    mydict = json.loads(self.input[item])
                    self.input[item]=mydict
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
            pids = [pids]
        if not pids:
            raise OperetoClientError('Process(s) identifiers must be provided.')
        return pids


    def _connect(self):
        if not self.session:
            self.session = requests.Session()
            self.session.auth = (self.input['opereto_user'], self.input['opereto_password'])
            response = self.session.post('%s/login'%self.input['opereto_host'], verify=False)
            if response.status_code>201:
                raise OperetoClientError('Failed to login to opereto server [%s]: %s'%(self.input['opereto_host'], response.reason))


    def _disconnect(self):
        if self.session:
            self.session.get(self.input['opereto_host']+'/logout', verify=False)


    def _call_rest_api(self, method, url, data={}, error=None, **kwargs):
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

        if response_json:
            if response_json['status']!='success':
                response_message = response_json.get('message') or ''
                if error:
                    response_message = error + ': ' + response_message
                if response_json.get('errors'):
                    response_message += response_json['errors']
                raise OperetoClientError(message=response_message, code=r.status_code)
            elif r.json().get('data'):
                return response_json['data']


    #### MICROSERVICES ####
    @apicall
    def search_services(self, start=0, limit=100, filter={}):
        request_data = {'start': start, 'limit': limit, 'filter': filter}
        return self._call_rest_api('post', '/search/services', data=request_data, error='Failed to search services')


    @apicall
    def get_service(self, service_id):
        return self._call_rest_api('get', '/services/'+service_id, error='Failed to fetch service information')


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

        url_suffix = '/versions/upload/%s'%mode
        if mode=='production':
            url_suffix+='/'+service_version
            if service_id:
                url_suffix+='/'+service_id
        return self._call_rest_api('post', url_suffix, files=files, error='Failed to upload service version')


    @apicall
    def import_service_version(self, repository_json, mode='production', service_version='default', service_id=None):
        request_data = {'repository': repository_json, 'mode': mode, 'service_version': service_version, 'id': service_id}
        return self._call_rest_api('post', '/versions', data=request_data, error='Failed to import service')


    @apicall
    def delete_service_version(self, service_id , service_version='default', mode='production'):
        return self._call_rest_api('delete', '/versions/'+service_id+'/'+service_version+'/'+mode, error='Failed to delete service')


    @apicall
    def delete_service(self, repository_json, mode='production', service_version='default', service_id=None):
        request_data = {'repository': repository_json, 'mode': mode, 'service_version': service_version, 'id': service_id}
        return self._call_rest_api('post', '/versions', data=request_data, error='Failed to import service')


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
    def get_all_agents(self):
        return self._call_rest_api('get', '/agents/all', error='Failed to fetch all agents.')


    @apicall
    def get_agent_properties(self, agent_id):
        return self._call_rest_api('get', '/agents/'+agent_id+'/properties', error='Failed to fetch agent [%s] properties'%agent_id)

    @apicall
    def get_all_agents(self):
        return self._call_rest_api('get', '/agents/all', error='Failed to fetch agents')


    @apicall
    def modify_agent_property(self, agent_id, key, value):
        return self._call_rest_api('post', '/agents/'+agent_id+'/properties', data={key: value}, error='Failed to modify agent [%s] properties'%agent_id)


    @apicall
    def get_agent_status(self, agent_id):
        return self._call_rest_api('get', '/agents/'+agent_id, error='Failed to fetch agent [%s] status'%agent_id)


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
        return str(pid)


    @apicall
    def modify_process_property(self, key, value, pid=None):
        if not pid and self.input.get('pid'):
            pid = self.input['pid']
        request_data={"key" : key, "value": value}
        return self._call_rest_api('post', '/processes/'+pid+'/output', data=request_data, error='Failed to output [%s]'%key)

    @apicall
    def modify_process_summary(self, pid, text):
        request_data={"id" : pid, "data": str(text)}
        return self._call_rest_api('post', '/processes/'+pid+'/summary', data=request_data, error='Failed to update process summary')


    @apicall
    def stop_process(self, pids, status='success'):
        if status not in process_result_statuses:
            raise OperetoClientError('Invalid process result [%s]'%status)
        if isinstance(pids, str):
            pids = [pids]
        for pid in pids:
            self._call_rest_api('post', '/processes/'+pid+'/terminate/'+status, error='Failed to stop process')


    @apicall
    def get_process_status(self, pid):
        return self._call_rest_api('get', '/processes/'+pid+'/status', error='Failed to fetch process status')


    @apicall
    def get_process_flow(self, pid):
        return self._call_rest_api('get', '/processes/'+pid+'/flow', error='Failed to fetch process information')


    @apicall
    def get_process_rca(self, pid):
        return self._call_rest_api('get', '/processes/'+pid+'/rca', error='Failed to fetch process information')


    @apicall
    def get_process_info(self, pid):
        return self._call_rest_api('get', '/processes/'+pid, error='Failed to fetch process information')

    @apicall
    def get_process_log(self, pid):
        return self._call_rest_api('get', '/processes/'+pid+'/log', error='Failed to fetch process log')


    @apicall
    def get_process_property(self, pid, name=None):
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
                self.logger.info('But it ended with status [%s]'%stat)
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
        if not pid:
            pid = self.input.get('pid')
        if pid:
            value = self._call_rest_api('get', '/processes/'+pid+'/cache?key=%s'%key, error='Failed to fetch process runtime cache')
        return value


    @apicall
    def set_process_runtime_cache(self, key, value, pid=None):
        if not pid:
            pid = self.input.get('pid')
        if pid:
            self._call_rest_api('post', '/processes/'+pid+'/cache', data={'key': key, 'value': value}, error='Failed to modify process runtime cache')



