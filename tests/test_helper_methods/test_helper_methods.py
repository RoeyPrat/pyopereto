import os
import uuid
import shutil


def zipfolder(zipname, target_dir):
    if target_dir.endswith('/'):
        target_dir = target_dir[:-1]
    base_dir =  os.path.basename(os.path.normpath(target_dir))
    root_dir = os.path.dirname(target_dir)
    shutil.make_archive(zipname, "zip", root_dir, base_dir)


def deploy_service(client, service_dir):
    zip_action_file = os.path.join('/tmp', str(uuid.uuid4())+'.action')
    zipfolder(zip_action_file, service_dir)
    print zip_action_file+'.zip'
    client.upload_service_version(service_zip_file=zip_action_file+'.zip')


def print_log_entries(client, pid):
    log_entries = client.get_process_log(pid)
    if log_entries:
        print 'Process log:'
        for entry in log_entries:
            print(entry['text'])


