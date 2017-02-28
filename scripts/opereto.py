#!python

"""Opereto Developer Tool

Usage:
  opereto.py sandbox list
  opereto.py sandbox purge
  opereto.py sandbox deploy all <services-directory>
  opereto.py sandbox deploy <service-directory>
  opereto.py sandbox run <service-name> [<title>] [<agent-name>] [<version>]
  opereto.py sandbox delete [<service-name>]
  opereto.py configure <service-directory>
  opereto.py production deploy all <services-directory> [<version>]
  opereto.py production deploy <service-directory> [<version>] [<service-name>]
  opereto.py production run <service-name> [<title>] [<agent-name>] [<version>] [--async]
  opereto.py production delete [<service-name>] [<version>]
  opereto.py production delete all <version>

Options:
    -h,--help           :show this help message
    service-name        :service name
    service-directory   :full path to your service directory
    version             :version string (e.g. 1.2.0, my_version..)
    title               : the process headline enclosed with double quotes

"""

from docopt import docopt
from pyopereto.client import OperetoClient, OperetoClientError
import os, sys
import uuid
import shutil
import yaml
import json
from os.path import expanduser
import logging
import logging.config

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


def zipfolder(zipname, target_dir):
    if target_dir.endswith('/'):
        target_dir = target_dir[:-1]
    base_dir =  os.path.basename(os.path.normpath(target_dir))
    root_dir = os.path.dirname(target_dir)
    shutil.make_archive(zipname, "zip", root_dir, base_dir)


def deploy(params):
    client = get_opereto_client()
    operations_mode = 'development'
    if params['production'] or params['<version>']:
        operations_mode = 'production'
    version=params['<version>'] or 'default'

    def deploy_service(service_directory, service_name=None):
        zip_action_file = os.path.join(TEMP_DIR, str(uuid.uuid4())+'.action')
        zipfolder(zip_action_file, service_directory)
        service_name = service_name or os.path.basename(os.path.normpath(service_directory))
        client.upload_service_version(service_zip_file=zip_action_file+'.zip', mode=operations_mode, service_version=version, service_id=service_name)
        if operations_mode=='production':
            logger.info('Service [%s] production version [%s] deployed successfuly.'%(service_name, version))
        else:
            logger.info('Service [%s] development version deployed successfully.'%service_name)

    if params['all']:
        deployed = 0
        not_deployed = 0
        service_directories = os.listdir(params['<services-directory>'])
        for service in service_directories:
            service_dir = os.path.join(params['<services-directory>'], service)
            if os.path.isdir(service_dir):
                try:
                    deploy_service(service_dir)
                    deployed+=1
                except OperetoClientError, e:
                    logger.error(e)
                    not_deployed+=1
                    continue
        logger.info('Total services deployed: %d'%deployed)
        if not_deployed>0:
            logger.error('Total services not deployed: %d'%not_deployed)

    else:
        deploy_service(params['<service-directory>'], params['<service-name>'])



def run(params):
    client = get_opereto_client()
    operations_mode = 'development'
    if params['production'] or params['<version>']:
        operations_mode = 'production'
    version=params['<version>'] or 'default'
    agent = params['<agent-name>'] or 'any'
    pid = client.create_process(service=params['<service-name>'], service_version=version, title=params['<title>'], agent=agent , mode=operations_mode)
    if operations_mode=='production':
        logger.info('A new process for service [%s] has been created: mode=%s, version=%s, pid=%s'%(params['<service-name>'], operations_mode, version, pid))
    else:
        logger.info('A new development process for service [%s] has been created: pid=%s'%(params['<service-name>'], pid))
    logger.info('{}/ui#dashboard/flow/{}'.format(opereto_host, pid))


def prepare(params):
    logger.info('-----------------------------------------------------------------------------\n  Preparing local argument files (not including builtin opereto parameters.  -----------------------------------------------------------------------------')

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
    return service_cmd


def delete(params):
    client = get_opereto_client()
    operations_mode = 'development'
    if params['<version>']:
        operations_mode = 'production'
    version=params['<version>'] or 'default'
    service_name = params['<service-name>']
    if not service_name and params['--all']:
        service_name='all'
    client.delete_service_version(service_id=service_name, service_version=version, mode=operations_mode)
    if operations_mode=='production':
        if service_name=='all':
            logger.info('All services of version %s have been delete.'%version)
        else:
            logger.info('Version [%s] of service [%s] has been deleted'%(service_name, version))


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



if __name__ == '__main__':
    try:
        arguments = docopt(__doc__, version='Opereto Developer Tool v1.0.0')
        if arguments['sandbox'] and arguments['list']:
            list_development_sandbox()
        elif arguments['sandbox'] and arguments['purge']:
            purge_development_sandbox()
        elif arguments['deploy']:
            deploy(arguments)
        elif arguments['run']:
            run(arguments)
        elif arguments['delete']:
            run(arguments)
        elif arguments['configure']:
            prepare(arguments)
    except OperetoClientError, e:
        logger.error(e)


