#!/usr/bin/python
from pyopereto.client import OperetoClient, OperetoClientError
import os
import json
import yaml
import zipfile
try:
    import boto
except ImportError:
    raise OperetoClientError('To use pyopereto dev utils, please install python boto library (e.g. pip install boto)')
import boto.s3.connection
from boto.s3.key import Key

if os.name=='nt':
    TEMP_DIR = 'C:\Temp'
else:
    TEMP_DIR = '/tmp'


class FilesStorage():

    def __init__(self, aws_access_key, aws_secret_key, aws_s3_bucket):
        self.bucket_name = aws_s3_bucket
        self.conn = boto.connect_s3(aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
        self.bucket = self.conn.get_bucket(self.bucket_name)

    def write_data(self, data, remote_file):
        k = Key(self.bucket)
        k.name = remote_file
        k.set_contents_from_filename(data)

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


class OperetoDevUtils():

    def __init__(self, **config):
        self.storage = FilesStorage(config['aws_access_key'],config['aws_secret_key'],config['aws_s3_bucket'])
        self.client = OperetoClient(opereto_host=config['opereto_host'], opereto_user=config['opereto_user'], opereto_password=config['opereto_password'])
        self.username = self.client.input.get('opereto_user')

    def cleanup_dev_repository(self):
        self.storage.delete_directory(prefix=self.username)

    def modify_dev_service(self, service_id, json_spec, description=None, agent_mapping=None):

        if 'repository' in json_spec:
            del json_spec['repository']
        repository  = {
            'repo_type': 'http',
            'url': 'https://s3.amazonaws.com/%s/%s/%s/action.zip'%(self.storage.bucket_name, self.username,service_id),
            'ot_dir': ''
        }
        json_spec['repository']=repository
        yaml_service_spec = yaml.dump(json_spec, indent=4, default_flow_style=False)
        self.client.verify_service(service_id, yaml_service_spec, description, agent_mapping)
        try:
            self.client.get_service(service_id)
        except OperetoClientError:
            self.client.modify_service(service_id, yaml_service_spec, description, agent_mapping)


    def delete_dev_service(self, service):
        self.storage.delete_directory(prefix=self.username+'/'+service)

    def upload_dev_service(self, service_dir, service_name=None, agents_mapping=None):

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

        print 'Service package will be saved in S3 temporary repositoy..'

        ### zip directory and store on s3
        zip_action_file = os.path.join(TEMP_DIR, self.username+'.'+service_name+'.action.zip')

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

        print 'Saving temp copy of service action files in AWS S3...'
        if not agents_mapping:
            if not os.path.exists(service_agent_mapping):
                service_agent_mapping=default_sam
            if os.path.exists(service_agent_mapping):
                with open(service_agent_mapping, 'r') as f:
                    agents_mapping = json.loads(f.read())

        self.modify_dev_service(service_name, service_spec, service_desc, agents_mapping)
        self.storage.write_file(self.username+'/'+service_name+'/'+'action.zip', zip_action_file)


