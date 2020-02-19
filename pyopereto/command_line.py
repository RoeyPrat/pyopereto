#!python

"""
Usage:
  opereto sandbox list
  opereto sandbox purge
  opereto sandbox deploy <service-directory> [--service-name=NAME | --recursive] [--comment=COMMENT]
  opereto sandbox run <service-name> [--agent=AGENT] [--title=TITLE] [--params=JSON_PARAMS] [--async]
  opereto sandbox delete <service-name>
  opereto local create <service-directory> [--agent=AGENT] [--title=TITLE] [--fetch-globals]
  opereto local remove <service-directory>
  opereto services list [<search_pattern>]
  opereto services deploy <service-directory> [--service-version=VERSION] [--service-name=NAME | --recursive] [--comment=COMMENT]
  opereto services run <service-name> [--agent=AGENT] [--title=TITLE]  [--params=JSON_PARAMS] [--service-version=VERSION] [--async]
  opereto services delete <service-name> [--service-version=VERSION]
  opereto services info <service-name> [--service-version=VERSION]
  opereto services versions <service-name>
  opereto version list <service-version>
  opereto version delete <service-version>
  opereto process <pid> [--info] [--properties] [--log] [--rca] [--flow] [--all]
  opereto process rerun <pid> [--title=TITLE] [--agent=AGENT] [--async]
  opereto agents list [<search_pattern>]
  opereto environments list [<search_pattern>]
  opereto environment <environment-name>
  opereto globals list [<search_pattern>]
  opereto (-h | --help)
  opereto --version

Options:
    search_pattern       : Textual search expression used to filter the search results.
                           If more than one word, must enclose with double quotes.

    service-name         : The service identifier (e.g. my_service)

    service-directory    : Full path to your service directory

    service-version      : Version string (e.g. 1.2.0, my_version..)

    comment              : Service deployment comment that will appear in the service audit log

    title                : The process headline enclosed with double quotes

    agent                : The agent identifier (e.g. my_test_agent)

    environment-name     : The environment identifier

    pid                  : The process identifier (e.g. 8XSVFdViKum)

    --fetch-globals      : Fetch the actual value of global parameters. In case of hidden globals, "********" will be returned for non-admin users

    --recursive          : Recursively deploy all micro services found in a given directory

    --async              : Run the service asynchronously (returns only the service process id)

    --params=JSON_PARAMS : Initiated process input parameters. Must be a JSON string
                           (e.g. --params='{"param1": "value", "param2": true, "param3": 100}')

    --info               : Prints process information
    --properties         : Prints process input and output properties
    --log                : Prints process execution log
    --flow               : Prints process flow near processes (ancestor and direct children)
    --rca                : Prints process root cause failure tree
                          (e.g all child processes that caused the failure)
    --all                : Print all process data entities

    -h,--help            : Show this help message
    --version            : Show this tool version
"""

import os, sys
sys.path.append('/Users/drorrusso/opereto/pyopereto')

import uuid
import shutil
import yaml
import json
from os.path import expanduser
import logging.config
import time
import signal
import pkg_resources
import tempfile
import subprocess
import re
import traceback
from docopt import docopt
from distutils.version import LooseVersion
from pyopereto.client import OperetoClient, OperetoClientError, process_running_statuses

try:
    VERSION = pkg_resources.get_distribution("pyopereto").version
except:
    VERSION=''

class OperetoCliError(Exception):

    def __init__(self, message, code=500):
        self.message = message
        self.code = code
        if os.environ.get('opereto_debug_mode'):
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_traceback,file=sys.stdout)

    def __str__(self):
        return self.message


logging.config.dictConfig({
    'version': 1,
    'formatters': {
        'colored': {
            '()': 'colorlog.ColoredFormatter',
            'format':
                "%(log_color)s%(message)s",
        }
    },
    'handlers': {
        'stream': {
            'class': 'logging.StreamHandler',
            'formatter': 'colored',
            'level': 'DEBUG'
        },
    },
    'loggers': {
        '': {
            'handlers': ['stream'],
            'level': 'DEBUG',
        },
    },
})

logger = logging.getLogger('OperetoCliTool')
TEMP_DIR = tempfile.gettempdir()
HOME_DIR = expanduser("~")
work_dir = os.getcwd()


RUNNING_PROCESS = None

pyopereto_latest_version_file = os.path.join(HOME_DIR,'.pyopereto.latest')
opereto_config_file = os.path.join(HOME_DIR,'opereto.yaml')
if not os.path.exists(opereto_config_file):
    opereto_config_file = 'arguments.yaml'
if not os.path.exists(opereto_config_file):
    raise Exception('Could not find opereto credentials file')

opereto_credentials_json = {}
with open(opereto_config_file, 'r') as f:
    opereto_credentials_json = yaml.load(f.read(), Loader=yaml.FullLoader)

opereto_host = opereto_credentials_json['opereto_host']
opereto_user = opereto_credentials_json['opereto_user']
opereto_email = opereto_credentials_json.get('opereto_email')
opereto_mobile = opereto_credentials_json.get('opereto_mobile')


def get_opereto_client():
    client = OperetoClient(opereto_host=opereto_credentials_json['opereto_host'], opereto_user=opereto_credentials_json['opereto_user'], opereto_password=opereto_credentials_json['opereto_password'])
    return client


def local(cmd, working_directory=os.getcwd()):
    print(cmd)
    p = subprocess.Popen(cmd, cwd=working_directory)
    retval = p.wait()
    return int(retval)


def get_service_directory(service_directory):
    if not os.path.exists(service_directory):
        raise Exception('Service directory [{}] does not exist.'.format(service_directory))
    if service_directory=='.':
        service_directory = os.getcwd()
    return service_directory


def get_process_rca(pid):
    client = get_opereto_client()
    print('Collecting RCA data..')
    rca_found=False
    for i in range(3):
        rca_json = client.get_process_rca(pid)
        if rca_json:
            rca_found=True
            logger.error(json.dumps(rca_json, indent=4))
            break
        time.sleep(5)
    if not rca_found:
        logger.error('No RCA data found for this process')

def zipfolder(zipname, target_dir):
    try:
        remove_service_dir=False
        stripped_target_dir = target_dir.rstrip("/")
        service_deploy_config_file = os.path.join(stripped_target_dir, 'service.deploy.json')
        temp_service_directory = stripped_target_dir
        if os.path.exists(service_deploy_config_file):
            temp_service_directory = os.path.join(TEMP_DIR, str(uuid.uuid4()))
            remove_service_dir=True
            shutil.copytree(stripped_target_dir, temp_service_directory)
            with open(service_deploy_config_file, 'r') as deploy_config:
                dc = json.loads(deploy_config.read())
                if 'include' in dc:
                    for path in dc['include']:
                        if path['type']=='relative':
                            fullpath = os.path.join(stripped_target_dir, path['path'])
                        elif path['type']=='absolute':
                            fullpath = path['path']
                        else:
                            raise OperetoCliError('Unknown or invalid include path type. Must be "relative" or "absolute"')
                        if os.path.exists(fullpath):
                            if fullpath.rstrip("/")!=stripped_target_dir:
                                if os.path.isdir(fullpath):
                                    shutil.copytree(fullpath,os.path.join(temp_service_directory, os.path.basename(os.path.normpath(fullpath))))
                                else:
                                    shutil.copy(fullpath, temp_service_directory)
                        else:
                            raise OperetoCliError('The include file or directory {} does not exist.'.format(fullpath))
                if 'exclude' in dc:
                    for path in dc['exclude']:
                        fullpath = os.path.join(temp_service_directory, path)
                        if os.path.exists(fullpath):
                            if fullpath.rstrip("/")!=temp_service_directory:
                                if os.path.isdir(fullpath):
                                    shutil.rmtree(fullpath)
                                else:
                                    os.remove(fullpath)
                if 'build' in dc:
                    exit_code = local(dc['build']['command'], working_directory=temp_service_directory)
                    if exit_code!=dc['build']['expected_exit_code']:
                        raise OperetoCliError('The build command failed (expected exit code={} actual exit code={}). Abort deployment..'.format(int(dc['build']['expected_exit_code']), exit_code))

        base_dir = os.path.basename(os.path.normpath(temp_service_directory))
        root_dir = os.path.dirname(temp_service_directory)
        shutil.make_archive(zipname, "zip", root_dir, base_dir)
    finally:
        if os.path.exists(temp_service_directory) and remove_service_dir:
            shutil.rmtree(temp_service_directory)


def deploy(params):
    client = get_opereto_client()
    operations_mode = 'development'
    if params['services']:
        operations_mode = 'production'
    version=params['--service-version'] or 'default'
    comment=params['--comment'] or ''

    def deploy_service(service_directory, service_name=None):
        service_name = service_name or os.path.basename(os.path.normpath(service_directory))
        try:
            zip_action_file = os.path.join(TEMP_DIR, str(uuid.uuid4())+'.action')
            zip_action_file_with_ext = zip_action_file + '.zip'
            zipfolder(zip_action_file, service_directory)
            file_size = os.stat(zip_action_file_with_ext).st_size
            if file_size>20*1000*1000:
                raise OperetoCliError('Service data size [{}] exceeds the maximum allowed [20MB]'.format(file_size))
            client.upload_service_version(service_zip_file=zip_action_file_with_ext, mode=operations_mode, service_version=version, service_id=service_name, comment=comment)
            if operations_mode=='production':
                logger.info('Service [%s] production version [%s] deployed successfuly.'%(service_name, version))
            else:
                logger.info('Service [%s] development version deployed successfully.'%service_name)
        except OperetoCliError as e:
            raise OperetoCliError('Service [%s]: %s'%(service_name, str(e)))
        except Exception as e:
            raise OperetoCliError('Service [%s] failed to deploy: %s'%(service_name, str(e)))
        finally:
            if os.path.exists(zip_action_file_with_ext):
                os.remove(zip_action_file_with_ext)

    def is_service_dir(dirpath):
        if not os.path.isdir(dirpath):
            return False
        if not os.path.exists(os.path.join(dirpath, 'service.yaml')):
            return False
        return True


    def deploy_root_service_dir(rootdir):
        if is_service_dir(rootdir):
            try:
                deploy_service(rootdir)
            except Exception as e:
                logger.error(e)
        elif os.path.isdir(rootdir):
            service_directories = os.listdir(rootdir)
            for directory in service_directories:
                service_dir = os.path.join(rootdir, directory)
                deploy_root_service_dir(service_dir)

    service_directory = get_service_directory(params['<service-directory>'])
    if params['--recursive']:
        deploy_root_service_dir(service_directory)
    else:
        deploy_service(service_directory, params['--service-name'])


def rerun(params):

    global RUNNING_PROCESS
    client = get_opereto_client()
    old_pid = params['<pid>']
    agent = params['--agent']
    title = params['--title']
    pid = client.rerun_process(old_pid, title=title, agent=agent)
    print('Re-running process [%s]..'%pid)

    if not params['--async']:
        RUNNING_PROCESS = pid
        status = wait_and_print_log(pid)
        RUNNING_PROCESS=None
        if status=='success':
            logger.info('Process ended with status: success')
        else:
            raise OperetoCliError('Process ended with status: %s'%status)
            get_process_rca(pid)
    print('View process flow at: {}/ui#dashboard/flow/{}'.format(opereto_host, pid))


def run(params):

    global RUNNING_PROCESS
    client = get_opereto_client()
    operations_mode = 'development'
    if params['services']:
        operations_mode = 'production'
    version=params['--service-version'] or 'default'
    agent = params['--agent'] or 'any'
    title = params['--title'] or None
    process_input_params={}
    try:
        if params['--params']:
            process_input_params = json.loads(params['--params'])
    except:
        raise OperetoCliError('Invalid process input properties. Please check that your parameters are provided as a json string')
        sys.exit(1)
    pid = client.create_process(service=params['<service-name>'], service_version=version, title=title, agent=agent , mode=operations_mode, properties=process_input_params)
    if operations_mode=='production':
        print('A new process for service [%s] has been created: mode=%s, version=%s, pid=%s'%(params['<service-name>'], operations_mode, version, pid))
    else:
        print('A new development process for service [%s] has been created: pid=%s'%(params['<service-name>'], pid))

    if not params['--async']:
        RUNNING_PROCESS = pid
        status = wait_and_print_log(pid)
        RUNNING_PROCESS=None
        if status=='success':
            logger.info('Process ended with status: success')
        else:
            raise OperetoCliError('Process ended with status: %s'%status)
            get_process_rca(pid)
    print('View process flow at: {}/ui#dashboard/flow/{}'.format(opereto_host, pid))


def local_dev(params):

    service_dir = get_service_directory(params['<service-directory>'])
    with open(os.path.join(params['<service-directory>'], 'service.yaml'), 'r') as f:
        spec = yaml.load(f.read(), Loader=yaml.FullLoader)
    if spec['type'] in ['cycle', 'container', 'builtin', 'record', 'testplan']:
        raise Exception('Execution of service type [%s] in local mode is not supported.'%spec['type'])

    json_arguments_file = os.path.join(params['<service-directory>'], 'arguments.json')
    yaml_arguments_file = os.path.join(params['<service-directory>'], 'arguments.yaml')

    client = get_opereto_client()


    def delete_local_dev_config():
        if os.path.exists(json_arguments_file):
            with open(json_arguments_file, 'r') as infile:
                arguments = json.loads(infile.read())
                if arguments.get('pid'):
                    try:
                        if client.get_process_status(arguments.get('pid')) == 'in_process':
                            logger.info('Stopping remote parent flow process [{}]..'.format(arguments['pid']))
                            client.stop_process([arguments.get('pid')])
                    except Exception as e:
                        logger.error(str(e))

            os.remove(json_arguments_file)

        if os.path.exists(yaml_arguments_file):
            os.remove(yaml_arguments_file)

        logger.info('Argument files in service directory [{}] have been removed.'.format(service_dir))


    ## Remove environment vars if exists (TBD)
    if params['remove']:
        delete_local_dev_config()
        print('Please remove any development default values from your servic.yaml before deploying it to production.')

    elif params['create']:

        delete_local_dev_config()

        parent_process_title = params['--title'] or 'Developer parent flow for user: {}'.format(opereto_user)
        ppid = client.create_process('local_dev_parent_flow', title=parent_process_title, agent='any', mode='development')
        client.wait_to_start(ppid)
        logger.info('A new parent process {} have been created.'.format(ppid))
        builtin_params = dict(pid=ppid, opereto_workspace=params['<service-directory>'], opereto_agent=params['--agent'],
                              opereto_source_flow_id=ppid, opereto_parent_flow_id=None, opereto_product_id=None,
                              opereto_service_version='', opereto_originator_username=opereto_user,
                              opereto_originator_email=opereto_email, opereto_originator_mobile=opereto_mobile,
                              opereto_execution_mode="development")
        builtin_params['opereto_timeout']=spec['timeout']

        # prepare arguments json
        arguments_json = builtin_params
        with open(opereto_config_file, 'r') as arguments_file:
            arguments_json.update(yaml.load(arguments_file.read(), Loader=yaml.FullLoader))
        if spec.get('item_properties'):
            for item in spec['item_properties']:
                value = item['value']
                if params['--fetch-globals']:
                    try:
                        global_rx = re.compile('GLOBALS\.([\w+|_|-]+)')
                        m = global_rx.match(value)
                        if m:
                            global_name = m.groups()[0]
                            value = client._call_rest_api('get', '/globals/{}'.format(global_name), error='Failed to get global')['value']
                    except Exception as e:
                        value = item['value']
                arguments_json[item['key']]=value

        # modify local argument files (json and yaml)
        with open(os.path.join(params['<service-directory>'], 'arguments.json'), 'w') as json_arguments_outfile:
            json.dump(arguments_json, json_arguments_outfile, indent=4, sort_keys=True)
        with open(os.path.join(params['<service-directory>'], 'arguments.yaml'), 'w') as yaml_arguments_outfile:
            yaml.dump(yaml.load(json.dumps(arguments_json), Loader=yaml.FullLoader), yaml_arguments_outfile, indent=4, default_flow_style=False)

        ## Add environment vars if exists (TBD)

        logger.info('Argument files in service directory [{}] have been created.'.format(service_dir))
        print('\nIn case you are developing a flow, you can view the created sub processes at:\n{}/ui#dashboard/flow/{}'.format(opereto_host, ppid))


def delete(params):
    client = get_opereto_client()
    operations_mode = 'development'
    if params['services']:
        operations_mode = 'production'
    version=params['--service-version'] or 'default'
    service_name = params['<service-name>']

    try:
        if operations_mode=='production':
            if version!='default':
                client.delete_service_version(service_id=service_name, service_version=version, mode=operations_mode)
            else:
                client.delete_service(service_id=service_name)
            logger.info('Service [%s] production version [%s] deleted successfuly.'%(service_name, version))
        else:
            client.delete_service_version(service_id=service_name, service_version=version, mode=operations_mode)
            logger.info('Service [%s] development version deleted successfully.'%service_name)
    except Exception as e:
        raise OperetoCliError('Service [{}] deletion failed: {}'.format(service_name, str(e)))


def purge_development_sandbox():
    client = get_opereto_client()
    try:
        client.purge_development_sandbox()
        logger.info('Purged development sandbox repository')
    except OperetoCliError as e:
        if e.message.find('does not exist'):
            logger.error('Development sandbox directory is empty.')

def list_development_sandbox():
    client = get_opereto_client()
    services_list = client.list_development_sandbox()
    if services_list:
        for service in sorted(services_list):
            logger.info(service)
    else:
        logger.error('Your development sandbox is empty.')

def list_services(arguments):
    client = get_opereto_client()
    filter=None
    if arguments['<search_pattern>']:
        filter={'generic': arguments['<search_pattern>']}
    services = client.search_services(filter=filter, start=0, limit=50000, fset='clitool')
    if services:
        print(json.dumps(services, indent=4, sort_keys=True))
    else:
        logger.error('No services found.')


def list_agents(arguments):
    client = get_opereto_client()
    filter=None
    if arguments['<search_pattern>']:
        filter={'generic': arguments['<search_pattern>']}
    agents = client.search_agents(filter=filter, start=0, limit=50000, fset='clitool')
    if agents:
        print(json.dumps(agents, indent=4, sort_keys=True))
    else:
        logger.error('No agents found.')

def list_globals(arguments):
    client = get_opereto_client()
    filter=None
    if arguments['<search_pattern>']:
        filter={'generic': arguments['<search_pattern>']}
    globals = client.search_globals(filter=filter, start=0, limit=50000)
    if globals:
        print(json.dumps(globals, indent=4, sort_keys=True))
    else:
        raise OperetoCliError('No globals found.')

def list_environments(arguments):
    client = get_opereto_client()
    filter = None
    if arguments['<search_pattern>']:
        filter={'generic': arguments['<search_pattern>']}
    envs = client.search_environments(filter=filter, start=0, limit=50000)
    if envs:
        print(json.dumps(envs, indent=4, sort_keys=True))
    else:
        logger.error('No environments found.')

def get_environment(arguments):
    client = get_opereto_client()
    env = client.get_environment(arguments['<environment-name>'])
    print(json.dumps(env, indent=4, sort_keys=True))


def get_service_versions(arguments):
    logger.info('Versions of service {}:'.format(arguments['<service-name>']))
    client = get_opereto_client()
    service = client.get_service(arguments['<service-name>'])
    print(json.dumps(service['versions'], indent=4, sort_keys=True))

def delete_services_version(arguments):
    client = get_opereto_client()
    service_version = arguments['<service-version>']
    if service_version=='default':
        raise OperetoCliError('Cannot delete default service version.')

    logger.info('Searching for all services of version {} (may take some time..)'.format(service_version))
    all_services = client.search_services(limit=50000)
    count = 0
    failed = 0
    for service in all_services:
        service_data = client.get_service(service['id'])
        if arguments['<service-version>'] in service_data['versions']:
            try:
                client.delete_service_version(service_data['id'], service_version=service_version)
                logger.info('Version {} of service {} has been deleted.'.format(service_data['id'], service_version))
                count+=1
            except OperetoCliError as e:
                logger.error('Failed to delete version {} of service {}: {}'.format(service_data['id'], service_version, e.message))
                failed+=1

    if count>0:
        logger.info('Version {} has been removed from {} services.'.format(arguments['<service-version>'], count))
        if failed > 0:
            logger.error('Failed to remove version {} from {} services.'.format(arguments['<service-version>'], count))
    else:
        logger.error('No services found for version {}.'.format(arguments['<service-version>']))


def list_services_version(arguments):
    logger.info('Listing all services of version {} (may take some time..)'.format(arguments['<service-version>']))
    client = get_opereto_client()
    all_services = client.search_services(limit=50000)
    count=0
    for service in all_services:
        service_data = client.get_service(service['id'])
        if arguments['<service-version>'] in service_data['versions']:
            count+=1
            print(service_data['id'])
    if count>0:
        logger.info('{} services found for version {}.'.format(count, arguments['<service-version>']))
    else:
        logger.error('No services found for version {}.'.format(arguments['<service-version>']))

def get_service_info(arguments):
    logger.info('Details of service {}:'.format(arguments['<service-name>']))
    client = get_opereto_client()
    version=arguments['--service-version'] or 'default'
    service = client.get_service_version(arguments['<service-name>'],version=version)

    logger.info('Service Description')
    logger.info('-------------------')
    print(service.get('description') or 'No description provided')

    logger.info('\n\nService Specification')
    logger.info('---------------------')

    try:
        print(yaml.dump(yaml.load(json.dumps(service['spec']), Loader=yaml.FullLoader), indent=4, default_flow_style=False))
    except:
        print(json.dumps(service['spec'], indent=4, sort_keys=True))

    logger.info('\n\nService Agents Mapping')
    logger.info('----------------------')
    print(json.dumps(service['sam'], indent=4, sort_keys=True))


def _print_log_entries(pid, s):
    client = get_opereto_client()
    log_entries = client.get_process_log(pid, start=s,limit=1000)
    if log_entries:
        for entry in log_entries:
            if entry['level']=='info':
                print(entry['text'])
            else:
                logger.error(entry['text'])
        return s+len(log_entries)
    return s


def wait_and_print_log(pid):
    client = get_opereto_client()
    start=0
    while(True):
        status = client.get_process_status(pid)
        new_start = _print_log_entries(pid, start)
        if new_start==start and status not in process_running_statuses:
            break
        start=new_start
        time.sleep(10)
    return status


def get_process(arguments):
    client = get_opereto_client()
    pid = arguments['<pid>']
    option_selected=False

    if arguments['--info'] or arguments['--all']:
        option_selected=True
        info = client.get_process_info(pid)
        print(json.dumps(info, indent=4, sort_keys=True))

    if arguments['--properties'] or arguments['--all']:
        option_selected=True
        properties = client.get_process_properties(pid)
        if properties:
            print(json.dumps(properties, indent=4, sort_keys=True))

    if arguments['--log'] or arguments['--all']:
        option_selected=True
        start=0
        new_start=_print_log_entries(pid,start)
        while new_start>start:
            start=new_start
            new_start=_print_log_entries(pid,start)

    if arguments['--flow'] or arguments['--all']:
        option_selected=True
        flow = client.get_process_flow(pid)
        if flow:
            print(json.dumps(flow, indent=4, sort_keys=True))

    if arguments['--rca'] or arguments['--all']:
        option_selected=True
        rca = client.get_process_rca(pid)
        if rca:
            print(json.dumps(rca, indent=4, sort_keys=True))

    if not option_selected:
        raise OperetoCliError('Please specify one if more process data items to retrieve (e.g. --info, --log).')


def _check_for_upgrade():

    try:

        def _check_latest_version():
            if VERSION!='':
                with open(pyopereto_latest_version_file, 'r') as latest_version:
                    latest = latest_version.read()
                    if latest:
                        if LooseVersion(latest)>LooseVersion(VERSION):
                            logger.warning('A newer version of pyopereto exists (v{}). Please upgrade using pip.'.format(latest))

        def _update_latest_version():
            with open(pyopereto_latest_version_file, 'w') as latest_version_file:
                client = get_opereto_client()
                all_releases = client._get_client_releases()
                latest_version = max(LooseVersion(s) for s in all_releases)
                latest_version_file.write(str(latest_version))

        if not os.path.exists(pyopereto_latest_version_file):
            _update_latest_version()
        elif time.time()>os.path.getmtime(pyopereto_latest_version_file)+12*3600:
            _update_latest_version()

        _check_latest_version()

    except Exception as e:
        logger.error('Failed to check for latest pyopereto version: {}'.format(str(e)))


def main():

    _check_for_upgrade()

    arguments = docopt(__doc__, version='Opereto CLI Tool v%s'%VERSION)
    def ctrlc_signal_handler(s, f):
        if arguments['run'] and RUNNING_PROCESS:
            sys.stderr.write('\nYou pressed Ctrl-C. Stopping running processes and aborting..')
            client = get_opereto_client()
            client.stop_process(RUNNING_PROCESS, status='terminated')
        else:
            sys.stderr.write('\nYou pressed Ctrl-C. Aborting..')
        os.kill(os.getpid(), signal.SIGTERM)

    try:
        signal.signal(signal.SIGINT, ctrlc_signal_handler)
        if arguments['sandbox'] and arguments['list']:
            list_development_sandbox()
        elif arguments['services'] and arguments['list']:
            list_services(arguments)
        elif arguments['services'] and arguments['info']:
            get_service_info(arguments)
        elif arguments['services'] and arguments['versions']:
            get_service_versions(arguments)
        elif arguments['process'] and arguments['rerun']:
            rerun(arguments)
        elif arguments['process']:
            get_process(arguments)
        elif arguments['version']:
            if arguments['delete']:
                delete_services_version(arguments)
            elif arguments['list']:
                list_services_version(arguments)
        elif arguments['agents'] and arguments['list']:
            list_agents(arguments)
        elif arguments['globals'] and arguments['list']:
            list_globals(arguments)
        elif arguments['environments'] and arguments['list']:
            list_environments(arguments)
        elif arguments['environment']:
            get_environment(arguments)
        elif arguments['sandbox'] and arguments['purge']:
            purge_development_sandbox()
        elif arguments['deploy']:
            deploy(arguments)
        elif arguments['run']:
            run(arguments)
        elif arguments['delete']:
            delete(arguments)
        elif arguments['local']:
            local_dev(arguments)

    except Exception as e:
        logger.error(str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()
