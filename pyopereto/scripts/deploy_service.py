from pyopereto.client import OperetoClient
from optparse import OptionParser
import os
import uuid
import shutil

TEMP_DIR = '/tmp'

def zipfolder(zipname, target_dir):
    if target_dir.endswith('/'):
        target_dir = target_dir[:-1]
    base_dir =  os.path.basename(os.path.normpath(options.dir))
    root_dir = os.path.dirname(target_dir)
    shutil.make_archive(zipname, "zip", root_dir, base_dir)


def parse_options():
    usage = "%prog -d path/to/service/directory [-s service] [-v version] [--production]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--dir", dest="dir", help="path to the service directory.")
    parser.add_option("-s", "--service", dest="service", help="service name (optional), if not provided, directory name will be used.")
    parser.add_option("-v", "--version", dest="version", help="service version (optional), if not provided, default version is used.")
    parser.add_option("--production", dest="production_mode", action='store_true', default=False, help="Specifies if to run in production mode")
    (options, args) = parser.parse_args()
    if not options.dir:
        parser.error('service directory must be provided.')
    return (options, args)


if __name__ == "__main__":
    (options, args) = parse_options()
    client = OperetoClient()
    zip_action_file = os.path.join(TEMP_DIR, str(uuid.uuid4())+'.action')
    zipfolder(zip_action_file, options.dir)
    operations_mode = 'development'
    if options.production_mode:
        operations_mode = 'production'
    if options.version:
        version=options.version
    else:
        version='default'
    client.upload_service_version(service_zip_file=zip_action_file+'.zip', mode=operations_mode, service_version=version, service_id=options.service)

