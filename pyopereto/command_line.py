#!python

"""Opereto Command Line Tool v1.0.0

Usage:
  opereto sandbox list
  opereto sandbox purge
  opereto sandbox deploy <service-directory> [--recursive]
  opereto sandbox run <service-name> [--agent=AGENT] [--title=TITLE] [--params=JSON_PARAMS] [--async]
  opereto sandbox delete <service-name>
  opereto configure <service-directory>
  opereto services list [<search_pattern>]
  opereto services deploy <service-directory> [--version=VERSION] [--service-name=NAME | --recursive]
  opereto services run <service-name> [--agent=AGENT] [--title=TITLE]  [--params=JSON_PARAMS] [--version=VERSION] [--async]
  opereto services delete <service-name> [--version=VERSION]
  opereto services info <service-name> [--version=VERSION]
  opereto versions <service-name>
  opereto process <pid> [--info] [--properties] [--log] [--rca] [--flow] [--all]
  opereto agents list [<search_pattern>]
  opereto environments list
  opereto globals list [<search_pattern>]
  opereto (-h | --help)

Options:
    search_pattern       : textual search expression used to filter the search results. If more than one word, must enclose with double quotes.
    service-name         : the service identifier (e.g. my_service)
    service-directory    : full path to your service directory
    version              : version string (e.g. 1.2.0, my_version..)
    title                : the process headline enclosed with double quotes
    agent                : the service identifier (e.g. my_test_agent)
    pid                  : the process identifier (e.g. 8XSVFdViKum)
    --recursive          : recursively deploy all micro services found in a given directory
    --async              : run the service asynchronously (returns only the service process id)
    --params=JSON_PARAMS : initiated process input parameters. Must be a JSON string (e.g. --params='{"param1": "value", "param2": true, "param3": 100}')
    --info               : print process information
    --properties         : print process input and output properties
    --log                : print process execution log
    --flow               : print process flow near processes (ancestor and direct children)
    --rca                : print process root cause failure tree (all child processes that caused the failure)
    --all                : print all process data entities
    -h,--help            : show this help message
"""


from docopt import docopt
from pyopereto.client import OperetoClient, OperetoClientError, process_running_statuses
import os, sys
import uuid
import shutil
import yaml
import json
from os.path import expanduser
import logging
import logging.config
import time
import signal


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

logger = logging.getLogger()


class OperetoDevToolError(Exception):
    def __init__(self, message, code=None):
        self.message = message
        self.code = code
    def __str__(self):
        return self.message


if sys.platform.startswith('win'):
    TEMP_DIR = 'C:\Temp'
else:
    TEMP_DIR = '/tmp'

HOME_DIR = expanduser("~")

work_dir = os.getcwd()
opereto_host = None

RUNNING_PROCESS = None

opereto_config_file = os.path.join(HOME_DIR,'opereto.yaml')
if not os.path.exists(opereto_config_file):
    opereto_config_file = 'arguments.yaml'
if not os.path.exists(opereto_config_file):
    raise Exception, 'Could not find opereto credentials file'

with open(opereto_config_file, 'r') as f:
    input = yaml.load(f.read())
    opereto_host = input['opereto_host']


def get_opereto_client():
    client = OperetoClient(opereto_host=input['opereto_host'], opereto_user=input['opereto_user'], opereto_password=input['opereto_password'])
    return client


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
    if target_dir.endswith('/'):
        target_dir = target_dir[:-1]
    base_dir =  os.path.basename(os.path.normpath(target_dir))
    root_dir = os.path.dirname(target_dir)
    shutil.make_archive(zipname, "zip", root_dir, base_dir)


def deploy(params):
    client = get_opereto_client()
    operations_mode = 'development'
    if params['services']:
        operations_mode = 'production'
    version=params['--version'] or 'default'

    def deploy_service(service_directory, service_name=None):
        service_name = service_name or os.path.basename(os.path.normpath(service_directory))
        try:
            zip_action_file = os.path.join(TEMP_DIR, str(uuid.uuid4())+'.action')
            zipfolder(zip_action_file, service_directory)
            client.upload_service_version(service_zip_file=zip_action_file+'.zip', mode=operations_mode, service_version=version, service_id=service_name)
            if operations_mode=='production':
                logger.info('Service [%s] production version [%s] deployed successfuly.'%(service_name, version))
            else:
                logger.info('Service [%s] development version deployed successfully.'%service_name)
        except OperetoClientError, e:
             raise e
        except:
             raise OperetoClientError(('Service [%s] failed to deploy.'%service_name))


    def is_service_dir(dirpath):
        if not os.path.isdir(dirpath):
            return False
        if not os.path.exists(os.path.join(dirpath, 'service.yaml')):
            return False
        return True


    def deploy_root_service_dir(rootdir):
        if is_service_dir(rootdir):
            deploy_service(rootdir)
        service_directories = os.listdir(rootdir)
        for directory in service_directories:
            service_dir = os.path.join(rootdir, directory)
            if is_service_dir(service_dir):
                deploy_root_service_dir(service_dir)

    if params['--recursive']:
        deploy_root_service_dir(params['<service-directory>'])
    else:
        deploy_service(params['<service-directory>'], params['--service-name'])


def run(params):

    global RUNNING_PROCESS
    client = get_opereto_client()
    operations_mode = 'development'
    if params['services']:
        operations_mode = 'production'
    version=params['--version'] or 'default'
    agent = params['--agent'] or 'any'
    title = params['--title'] or None
    process_input_params={}
    try:
        if params['--params']:
            process_input_params = json.loads(params['--params'])
    except:
        raise OperetoClientError('Invalid process input properties. Please check that your parameters are provided as a json string')
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
            raise OperetoClientError('Process ended with status: %s'%status)
            get_process_rca(pid)
    print('View process flow at: {}/ui#dashboard/flow/{}'.format(opereto_host, pid))


def prepare(params):
    with open(os.path.join(params['<service-directory>'], 'service.yaml'), 'r') as f:
        spec = yaml.load(f.read())
    if spec['type'] in ['cycle', 'container']:
        raise Exception, 'Execution of service type [%s] in local mode is not supported.'%spec['type']
    service_cmd = spec['cmd']
    with open(opereto_config_file, 'r') as arguments_file:
        arguments_json = yaml.load(arguments_file.read())
    if spec.get('item_properties'):
        for item in spec['item_properties']:
            arguments_json[item['key']]=item['value']
    with open(os.path.join(params['<service-directory>'], 'arguments.json'), 'w') as json_arguments_outfile:
        json.dump(arguments_json, json_arguments_outfile, indent=4, sort_keys=True)
    with open(os.path.join(params['<service-directory>'], 'arguments.yaml'), 'w') as yaml_arguments_outfile:
        yaml.dump(yaml.load(json.dumps(arguments_json)), yaml_arguments_outfile, indent=4, default_flow_style=False)
    logger.info('Local argument files updated successfully.')
    print 'To run the service locally, please go to service directory and run: %s\n'%service_cmd
    return service_cmd


def delete(params):
    client = get_opereto_client()
    operations_mode = 'development'
    if params['services']:
        operations_mode = 'production'
    version=params['--version'] or 'default'
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
    except OperetoClientError, e:
        raise e
    except:
        raise OperetoClientError('Service [%s] failed to delete.'%service_name)


def purge_development_sandbox():
    client = get_opereto_client()
    try:
        client.purge_development_sandbox()
        logger.info('Purged development sandbox repository')
    except OperetoClientError, e:
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
    services = client.search_services(filter=filter, start=0, limit=1000, fset='clitool')
    if services:
        print json.dumps(services, indent=4, sort_keys=True)
    else:
        logger.error('No services found.')


def list_agents(arguments):
    client = get_opereto_client()
    filter=None
    if arguments['<search_pattern>']:
        filter={'generic': arguments['<search_pattern>']}
    agents = client.search_agents(filter=filter, start=0, limit=1000, fset='clitool')
    if agents:
        print json.dumps(agents, indent=4, sort_keys=True)
    else:
        logger.error('No agents found.')

def list_globals(arguments):
    client = get_opereto_client()
    filter=None
    if arguments['<search_pattern>']:
        filter={'generic': arguments['<search_pattern>']}
    globals = client.search_globals(filter=filter, start=0, limit=1000)
    if globals:
        print json.dumps(globals, indent=4, sort_keys=True)
    else:
        raise OperetoClientError('No globals found.')

def list_environments(arguments):
    client = get_opereto_client()
    envs = client.search_environments()
    if envs:
        print json.dumps(envs, indent=4, sort_keys=True)
    else:
        logger.error('No environments found.')

def get_service_versions(arguments):
    logger.info('Versions of service {}:'.format(arguments['<service-name>']))
    client = get_opereto_client()
    service = client.get_service(arguments['<service-name>'])
    print json.dumps(service['versions'], indent=4, sort_keys=True)


def get_service_info(arguments):
    logger.info('Details of service {}:'.format(arguments['<service-name>']))
    client = get_opereto_client()
    version=arguments['--version'] or 'default'
    service = client.get_service_version(arguments['<service-name>'],version=version)

    logger.info('Service Description')
    logger.info('-------------------')
    print service.get('description') or 'No description provided'

    logger.info('\n\nService Specification')
    logger.info('---------------------')

    try:
        print yaml.dump(yaml.load(json.dumps(service['spec'])), indent=4, default_flow_style=False)
    except:
        print json.dumps(service['spec'], indent=4, sort_keys=True)

    logger.info('\n\nService Agents Mapping')
    logger.info('----------------------')
    print json.dumps(service['sam'], indent=4, sort_keys=True)


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
        print json.dumps(info, indent=4, sort_keys=True)

    if arguments['--properties'] or arguments['--all']:
        option_selected=True
        properties = client.get_process_properties(pid)
        if properties:
            print json.dumps(properties, indent=4, sort_keys=True)

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
            print json.dumps(flow, indent=4, sort_keys=True)

    if arguments['--rca'] or arguments['--all']:
        option_selected=True
        rca = client.get_process_rca(pid)
        if rca:
            print json.dumps(rca, indent=4, sort_keys=True)

    if not option_selected:
        raise OperetoClientError('Please specify one if more process data items to retrieve (e.g. --info, --log).')


def main():
    arguments = docopt(__doc__)
    def ctrlc_signal_handler(s, f):
        if arguments['run'] and RUNNING_PROCESS:
            print >> sys.stderr, '\nYou pressed Ctrl-C. Stopping running processes and aborting..'
            client = get_opereto_client()
            client.stop_process(RUNNING_PROCESS, status='terminated')
        else:
            print >> sys.stderr, '\nYou pressed Ctrl-C. Aborting..'
        os.kill(os.getpid(), signal.SIGTERM)

    try:
        signal.signal(signal.SIGINT, ctrlc_signal_handler)
        if arguments['sandbox'] and arguments['list']:
            list_development_sandbox()
        elif arguments['services'] and arguments['list']:
            list_services(arguments)
        elif arguments['services'] and arguments['info']:
            get_service_info(arguments)
        elif arguments['process']:
            get_process(arguments)
        elif arguments['versions']:
            get_service_versions(arguments)
        elif arguments['agents'] and arguments['list']:
            list_agents(arguments)
        elif arguments['globals'] and arguments['list']:
            list_globals(arguments)
        elif arguments['environments'] and arguments['list']:
            list_environments(arguments)
        elif arguments['sandbox'] and arguments['purge']:
            purge_development_sandbox()
        elif arguments['deploy']:
            deploy(arguments)
        elif arguments['run']:
            run(arguments)
        elif arguments['delete']:
            delete(arguments)
        elif arguments['configure']:
            prepare(arguments)
    except Exception, e:
        logger.error(str(e))
        sys.exit(1)



if __name__ == "__main__":
    main()
