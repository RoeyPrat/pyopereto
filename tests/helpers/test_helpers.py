import os
import uuid
import shutil
import tempfile


def zip_and_upload(opereto_client, service_folder, service_id, mode='production', service_version='default'):
    zip_action_file = zip_folder(os.path.join(os.path.dirname(__file__), service_folder))
    opereto_client.upload_service_version (service_zip_file=zip_action_file + '.zip', mode=mode,
                                           service_version=service_version, service_id=service_id)


def zip_folder( target_dir):

    zip_action_file = os.path.join (tempfile.gettempdir (), str (uuid.uuid4()) + '.action')

    if target_dir.endswith('/'):
        target_dir = target_dir[:-1]
    base_dir = os.path.basename(os.path.normpath(target_dir))
    root_dir = os.path.dirname(target_dir)
    shutil.make_archive(zip_action_file, "zip", root_dir, base_dir)
    return zip_action_file


def print_log_entries(client, pid):
    log_entries = client.get_process_log(pid)
    if log_entries:
        print ('Process log:')
        for entry in log_entries:
            print(entry['text'])


