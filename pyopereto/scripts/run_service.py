#!/usr/bin/python
from pyopereto.client import OperetoClient
from optparse import OptionParser

def parse_options():
    usage = "%prog -s service [-t title] [-a agent] [-v version] [--production]"
    parser = OptionParser(usage=usage)
    parser.add_option("-s", "--service", dest="service", help="service name.")
    parser.add_option("-v", "--version", dest="version", help="service version specification (optional), for instance: 1.1.0-12.")
    parser.add_option("-t", "--title", dest="title", help="process title (optional).")
    parser.add_option("-a", "--agent", dest="agent", default='any', help="agent name (optional), default is 'any'.")
    parser.add_option("--production", dest="production", action='store_true', default=False, help="Runs the default production version. The same as specifying [--version default]")

    (options, args) = parser.parse_args()
    if not options.service:
        parser.error('service must be provided.')

    return (options, args)

if __name__ == "__main__":
    (options, args) = parse_options()
    client = OperetoClient()
    operations_mode = 'development'
    if options.production or options.version:
        operations_mode = 'production'
    version=options.version
    if not version:
        version='default'

    pid = client.create_process(service=options.service, service_version=version, title=options.title, agent=options.agent , mode=operations_mode)
    if operations_mode=='production':
        print 'A new process for service [%s] has been created: mode=%s, version=%s, pid=%s'%(options.service, operations_mode, options.version, pid)
    else:
        print 'A new development process for service [%s] has been created: pid=%s'%(options.service, pid)

