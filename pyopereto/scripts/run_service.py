from pyopereto.client import OperetoClient
from optparse import OptionParser
import yaml

def parse_options():
    usage = "%prog -s service [-t title] [-a agent] [-v version] [--dev]"
    parser = OptionParser(usage=usage)
    parser.add_option("-s", "--service", dest="service", help="service name.")
    parser.add_option("-v", "--version", dest="version", help="service version specification (optional), for instance: 1.1.0-12.")
    parser.add_option("-t", "--title", dest="title", help="process title (optional).")
    parser.add_option("-a", "--agent", dest="agent", default='any', help="agent name (optional), default is 'any'.")
    parser.add_option("--dev", dest="dev_mode", action='store_true', default=False, help="Specifies if to run in development mode")

    (options, args) = parser.parse_args()
    if not options.service:
        parser.error('service must be provided.')

    return (options, args)


if __name__ == "__main__":
    (options, args) = parse_options()
    with open('config.yaml', 'r') as f:
        config = yaml.load(f.read())
    client = OperetoClient(**config)
    operations_mode = 'production'
    if options.dev_mode:
        operations_mode = 'development'

    pid = client.create_process(service=options.service, service_version=options.version, title=options.title, agent=options.agent , mode=operations_mode)
    print 'A new process for service [%s] has been created: mode=%s, version=%s, pid=%s'%(options.service, operations_mode, options.version, pid)