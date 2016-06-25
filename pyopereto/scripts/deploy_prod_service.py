from pyopereto.dev_utils import OperetoDevUtils
from optparse import OptionParser
import yaml

def parse_options():
    usage = "%prog -d path/to/service/directory [-s service] [--lock]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--dir", dest="dir", help="path to the service directory.")
    parser.add_option("-s", "--service", dest="service", help="service name (optional), if not provided, directory name will be used.")
    parser.add_option("--lock", dest="production_lock", action='store_true', default=False, help="Lock for production. Once locked, only admin can modify this service.")

    (options, args) = parser.parse_args()
    if not options.dir:
        parser.error('service directory must be provided.')

    return (options, args)

if __name__ == "__main__":
    (options, args) = parse_options()
    with open('config.yaml', 'r') as f:
        config = yaml.load(f.read())

    du = OperetoDevUtils(**config)
    du.modify_production_service(service_dir=options.dir, service_name=options.service, production_lock=options.production_lock)

