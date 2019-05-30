import os, json, shutil, uuid, sys, tempfile
from boto.s3.connection import S3Connection
from boto.s3.key import Key
import subprocess

TEMP_DIR = tempfile.gettempdir()

class OperetoAwsS3PackagesManager():

    def __init__(self, package_path, bucket_name, access_key, secret_key, target_path):

        self.conn = S3Connection(access_key, secret_key)
        self.bucket_name = bucket_name
        self.packages_json = []
        self.current_directory = package_path
        self.services_directory = os.path.join(self.current_directory, 'services')
        self.packages_directory = os.path.join(self.current_directory, 'package')
        self.target_path = target_path
        self.package_repo_url = "https://s3.amazonaws.com/{}/{}".format(self.bucket_name, self.target_path)
        self.bucket = self.conn.get_bucket(self.bucket_name)

    def zipfolder(self, zipname, target_dir):
        if target_dir.endswith('/'):
            target_dir = target_dir[:-1]
        base_dir = os.path.basename(os.path.normpath(target_dir))
        root_dir = os.path.dirname(target_dir)
        shutil.make_archive(zipname, "zip", root_dir, base_dir)

    def save_file(self, remote_file, local_file_path, content_type=None):
        k = Key(self.bucket)
        k.name = self.target_path+'/'+remote_file
        if content_type:
             k.content_type = content_type
        k.set_contents_from_filename(local_file_path)
        k.set_acl('public-read')

    def save_json_data(self, remote_file, data):
        k = Key(self.bucket)
        k.name = self.target_path+'/'+remote_file
        k.content_type = 'application/json'
        k.set_contents_from_string(data)
        k.set_acl('public-read')

    def get_json_data(self, remote_file):
        k = Key(self.bucket)
        k.name = self.target_path+'/'+remote_file
        return json.loads(k.get_contents_as_string())

    def deploy_package(self, package_id):
        print('Deploying package {}'.format(package_id))
        source_dir = os.path.join(TEMP_DIR, package_id)
        zip_action_file = os.path.join(TEMP_DIR, str(uuid.uuid4())+'.action')
        self.zipfolder(zip_action_file, source_dir)
        self.save_file('{}.zip'.format(package_id), zip_action_file+'.zip')
        os.remove(zip_action_file+'.zip')

    def local(self, cmd, working_directory=os.getcwd()):
        print cmd
        p = subprocess.Popen(cmd, cwd=working_directory)
        retval = p.wait()
        return int(retval)

    def deploy_service(self, package_temp_dir, id, attr):
        print('Adding service {}'.format(id))
        source_dir = os.path.join(self.services_directory, attr['source_dir'])
        dest_dir = os.path.join(package_temp_dir,id)
        shutil.copytree(source_dir,dest_dir)
        service_deploy_config_file = os.path.join(source_dir, 'service.deploy.json')

        if os.path.exists(service_deploy_config_file):
            with open(service_deploy_config_file, 'r') as deploy_config:
                dc = json.loads(deploy_config.read())
                if 'include' in dc:
                    for path in dc['include']:
                        if path['type'] == 'relative':
                            fullpath = os.path.join(source_dir, path['path'])
                        elif path['type'] == 'absolute':
                            fullpath = path['path']
                        else:
                            raise Exception(
                                'Unknown or invalid include path type. Must be "relative" or "absolute"')
                        if os.path.exists(fullpath):
                            if fullpath.rstrip("/") != dest_dir:
                                if os.path.isdir(fullpath):
                                    shutil.copytree(fullpath, os.path.join(dest_dir, os.path.basename(
                                        os.path.normpath(fullpath))))
                                else:
                                    shutil.copy(fullpath, dest_dir)
                        else:
                            raise Exception(
                                'The include file or directory {} does not exist.'.format(fullpath))
                if 'build' in dc:
                    exit_code = self.local(dc['build']['command'], working_directory=dest_dir)
                    if exit_code != dc['build']['expected_exit_code']:
                        raise Exception(
                            'The build command failed (expected exit code={} actual exit code={}). Abort deployment..'.format(
                                int(dc['build']['expected_exit_code']), exit_code))

    def deploy_packages_json(self):
        self.save_json_data('packages.json', json.dumps(self.packages_json, indent=4, sort_keys=True))

    def modify_packages_json(self):
        current_packages_json = self.get_json_data('packages.json')
        found=False
        for package in current_packages_json:
            if package['id']==self.package:
                current_packages_json[current_packages_json.index(package)] = self.packages_json[0]
                found=True
                break
        if not found:
            current_packages_json.append(self.packages_json[0])

        self.save_json_data('packages.json', json.dumps(current_packages_json, indent=4, sort_keys=True))

    def deploy(self):
        print('Deploying packages to s3 (bucket={})..'.format(self.bucket_name))
        for p_dir in [d for d in os.listdir(self.packages_directory) if os.path.isdir(d)]:
            package_spec_file = os.path.join(self.packages_directory, p_dir, 'package.json')
            if os.path.exists(package_spec_file):
                with open(package_spec_file, 'r') as psf:
                    package_spec = json.loads(psf.read())
                    package_id = package_spec['id']
                    package_temp_dir = os.path.join(TEMP_DIR, package_id)
                    if os.path.exists(package_temp_dir):
                        shutil.rmtree(package_temp_dir)
                    os.mkdir(package_temp_dir)
                    services_to_upload = package_spec['services']
                    for id, attr in list(services_to_upload.items()):
                        self.deploy_service(package_temp_dir, id, attr)
                        package_spec['services'][id]= {
                            "repository": {
                                "ot_dir": package_id + '/' + id
                            },
                            "info": attr['info']
                        }
                icon_file_name = package_spec['large_icon']
                icon_file = os.path.join(self.packages_directory, p_dir, icon_file_name)
                new_icon_name = '{}.jpg'.format(package_id)
                self.save_file(new_icon_name, icon_file, content_type='img/jpg')
                package_spec['large_icon']='{}/{}'.format(self.package_repo_url, new_icon_name)
                package_spec['repository']= {
                    "repo_type": "http",
                    "url": self.package_repo_url+'/{}.zip'.format(package_id)
                }
                self.deploy_package(package_id)
                self.packages_json.append(package_spec)
            else:
                raise Exception('[{}] is not a valid package directory.'.format(p_dir))

        self.deploy_packages_json()

