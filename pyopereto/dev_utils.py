#!/usr/bin/python
from pyopereto.client import OperetoClient, OperetoClientError
import os,sys
import json
import yaml
import zipfile
try:
    import boto
except ImportError:
    raise OperetoClientError('To use pyopereto dev utils, please install python boto library (e.g. pip install boto)')
import boto.s3.connection
from boto.s3.key import Key
import hashlib
import logging
FORMAT = '%(asctime)s: [%(levelname)s] %(message)s'
logging.basicConfig(stream=sys.stdout, format=FORMAT, level=logging.ERROR)
logger = logging.getLogger('OperetoDevUtils')
logging.getLogger("OperetoDevUtils").setLevel(logging.INFO)


if os.name=='nt':
    TEMP_DIR = 'C:\Temp'
else:
    TEMP_DIR = '/tmp'

non_action_services = ['cycle', 'container', 'feedback']

def get_file_md5sum(file):
    md5 = hashlib.md5()
    with open(file,'rb') as f:
        for chunk in iter(lambda: f.read(8192), ''):
            md5.update(chunk)
    return md5.hexdigest()


class FilesStorage():

    def __init__(self, aws_access_key, aws_secret_key, aws_s3_bucket):
        self.bucket_name = aws_s3_bucket
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.conn = boto.connect_s3(aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
        self.bucket = self.conn.get_bucket(self.bucket_name)

    def write_data(self, data, remote_file):
        k = Key(self.bucket)
        k.name = remote_file
        k.set_contents_from_string(data)

    def read_data(self, remote_file):
        k = Key(self.bucket)
        k.name = remote_file
        return k.get_contents_as_string()

    def delete_file(self, remote_file):
        k = Key(self.bucket)
        k.key = remote_file
        self.bucket.delete_key(k)

    def delete_directory(self, prefix):
        bucket_list_result_set = self.bucket.list(prefix=prefix)
        self.bucket.delete_keys([key.name for key in bucket_list_result_set])


    def write_file(self, remote_file, local_file_path, public=False):
        k = Key(self.bucket)
        k.name = remote_file
        k.set_contents_from_filename(local_file_path)
        if public:
            k.set_acl('public-read')

    def read_file(self, remote_file, local_file_path):
        k = Key(self.bucket)
        k.name = remote_file
        k.get_contents_to_filename(local_file_path)


class OperetoServiceUtils():

    def __init__(self, access_key=None, secret_key=None, bucket_name=None, **config):
        if access_key and secret_key and bucket_name:
            self.storage = FilesStorage(access_key, secret_key, bucket_name)
        self.client = OperetoClient(opereto_host=config['opereto_host'], opereto_user=config['opereto_user'], opereto_password=config['opereto_password'])
        self.username = self.client.input.get('opereto_user')

    def _cleanup_repository(self, path):
        self.storage.delete_directory(prefix=path)

    def create_service(self, service_id, json_spec, description=None, agent_mapping=None):

        if json_spec['type'] not in non_action_services:
            if 'repository' in json_spec:
                del json_spec['repository']
            repository  = {
                'repo_type': 's3',
                'access_key': self.storage.aws_access_key,
                'secret_key': self.storage.aws_secret_key,
                'bucket': self.storage.bucket_name,
                'ot_dir': '%s/%s'%(self.username, service_id)
            }
            json_spec['repository']=repository
        yaml_service_spec = yaml.dump(json_spec, indent=4, default_flow_style=False)
        self.client.verify_service(service_id, yaml_service_spec, description, agent_mapping)
        self.modify_service(service_id=service_id, yaml_service_spec=yaml_service_spec, description=description, agent_mapping=agent_mapping)


    def _delete_service(self, path):
        self.storage.delete_directory(prefix=path)


    def _read_service_directory(self, service_dir, service_name=None):

        service_dir = service_dir.rstrip('/')
        if not service_name:
            service_name = os.path.basename(service_dir)

        default_service_yaml = os.path.join(service_dir, 'service.yaml')
        default_service_readme = os.path.join(service_dir, 'service.md')
        default_sam = os.path.join(service_dir, 'service.sam.json')
        service_yaml = os.path.join(service_dir, '%s.yaml' % service_name)
        service_readme = os.path.join(service_dir, '%s.md' % service_name)
        service_agent_mapping = os.path.join(service_dir, '%s.sam.json' % service_name)
        if not os.path.exists(service_yaml):
            service_yaml=default_service_yaml
        if not os.path.exists(service_yaml):
            raise OperetoClientError('Could not find service yaml file in the service directory.')
        with open(service_yaml, 'r') as stream:
            service_spec = yaml.load(stream)
        service_desc=None
        if not os.path.exists(service_readme):
            service_readme=default_service_readme
        if os.path.exists(service_readme):
            with open(service_readme, 'r') as f:
                service_desc = f.read()

        agents_mapping = None
        if not os.path.exists(service_agent_mapping):
            service_agent_mapping=default_sam
        if os.path.exists(service_agent_mapping):
            with open(service_agent_mapping, 'r') as f:
                agents_mapping = json.loads(f.read())

        return (service_name, service_spec,service_desc,agents_mapping)




    def _upload_service(self, service_dir, file_prefix, remote_repo_dir, service_name=None, agents_mapping=None, flush_repo=False):

        if flush_repo:
            logger.info('Flushing service repository..')
            self.cleanup_repository()

        (service_id, service_spec,service_desc,default_agents_mapping) = self._read_service_directory(service_dir, service_name)


        ### zip directory and store on s3
        zip_action_file = os.path.join(TEMP_DIR, file_prefix+'.action.zip')
        signature_file = os.path.join(TEMP_DIR, file_prefix+'.md5')


        def zipfolder(zipname, target_dir):
            if target_dir.endswith('/'):
                target_dir = target_dir[:-1]
            zipobj = zipfile.ZipFile(zipname, 'w', zipfile.ZIP_DEFLATED)
            rootlen = len(target_dir) + 1
            for base, dirs, files in os.walk(target_dir):
                for file in files:
                    fn = os.path.join(base, file)
                    zipobj.write(fn, fn[rootlen:])

        zipfolder(zip_action_file, service_dir)

        zip_action_md5 = get_file_md5sum(zip_action_file)
        with open(signature_file, 'w') as sf:
            sf.write(zip_action_md5)

        if not agents_mapping:
            agents_mapping=default_agents_mapping

        remote_action_file = remote_repo_dir+'/'+'action.zip'
        remote_signature_file = remote_repo_dir+'/.md5'
        self.storage.write_file(remote_action_file, zip_action_file)
        self.storage.write_file(remote_signature_file, signature_file)

        logger.info('Saved a temp copy of service action files in the S3 repository at (%s)...'%os.path.join(self.storage.bucket_name, remote_repo_dir))
        self.create_service(service_id, service_spec, service_desc, agents_mapping)


class OperetoDevUtils(OperetoServiceUtils):

    def __init__(self, **config):
        OperetoServiceUtils.__init__(self, config['aws']['development']['access_key'],config['aws']['development']['secret_key'],config['aws']['development']['bucket_name'], **config)

    def cleanup_repository(self):
        self._cleanup_repository(self.username)

    def delete_service(self, service):
        self._delete_service(self.username+'/'+service)

    def modify_service(self, service_id, yaml_service_spec, description=None, agent_mapping=None):
        try:
            self.client.get_service(service_id)
        except OperetoClientError:
            self.client.modify_service(service_id, yaml_service_spec, description, agent_mapping)
            logger.info('Created a new service in opereto.')

    def override_service(self, service_id, json_spec, description=None, agent_mapping=None):
        if json_spec['type'] not in non_action_services:
            if 'repository' in json_spec:
                del json_spec['repository']
            repository  = {
                'repo_type': 's3',
                'access_key': self.storage.aws_access_key,
                'secret_key': self.storage.aws_secret_key,
                'bucket': self.storage.bucket_name,
                'ot_dir': '%s/%s'%(self.username, service_id)
            }
            json_spec['repository']=repository
        yaml_service_spec = yaml.dump(json_spec, indent=4, default_flow_style=False)
        self.client.verify_service(service_id, yaml_service_spec, description, agent_mapping)
        self.client.modify_service(service_id, yaml_service_spec, description, agent_mapping)
        logger.info('Modified production service to point to development repository.')


    def modify_production_service(self, service_dir, service_name=None, production_lock=False):

        (service_id, service_spec,service_desc,agents_mapping) = self._read_service_directory(service_dir, service_name)
        if production_lock:
            service_spec['production']=True
        yaml_service_spec = yaml.dump(service_spec, indent=4, default_flow_style=False)
        if service_spec.get('repository'):
            self.client.verify_service(service_id, yaml_service_spec, service_desc, agents_mapping)
            self.client.modify_service(service_id, yaml_service_spec, service_desc, agents_mapping)
        else:
            self.override_service(service_id, service_spec, service_desc, agents_mapping)


    def upload_service(self, service_dir, service_name=None, agents_mapping=None, flush_repo=False):
        service_dir = service_dir.rstrip('/')
        if not service_name:
            service_name = os.path.basename(service_dir)
        self._upload_service(service_dir, self.username+'.'+service_name , self.username+'/'+service_name, service_name=service_name, agents_mapping=agents_mapping, flush_repo=flush_repo)


class OperetoVersionsUtils(OperetoServiceUtils):

    def __init__(self, **config):
        OperetoServiceUtils.__init__(self, config['aws']['versions']['access_key'],config['aws']['versions']['secret_key'],config['aws']['versions']['bucket_name'], **config)

    def cleanup_repository(self):
        self._cleanup_repository(self.username)

    def delete_service(self, service):
        self._delete_service(self.username+'/'+service)

    def modify_service(self, service_id, **kwargs):
        try:
            self.client.get_service(service_id)
        except OperetoClientError:
            raise Exception, 'Service [%s] is invalid or does not exist in Opereto'%service_id

    def upload_service(self, service_dir, service_version, service_name=None, agents_mapping=None, flush_repo=False):
        if service_dir and service_version:
            service_dir = service_dir.rstrip('/')
            if not service_name:
                service_name = os.path.basename(service_dir)
            self._upload_service(service_dir, service_name+'.'+service_version , service_name+'/'+service_version, service_name=service_name, agents_mapping=agents_mapping, flush_repo=flush_repo)


