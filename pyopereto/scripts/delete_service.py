#!/usr/bin/python
from pyopereto.client import OperetoClient
from optparse import OptionParser

def parse_options():
    usage = "%prog -s service [-v version]"
    parser = OptionParser(usage=usage)
    parser.add_option("-s", "--service", dest="service", help="service name.")
    parser.add_option("-v", "--version", dest="version", help="delete a specific service production version, for instance: 1.1.0-12.")

    (options, args) = parser.parse_args()
    if not options.service:
        parser.error('service must be provided.')

    return (options, args)

if __name__ == "__main__":
    (options, args) = parse_options()
    client = OperetoClient()
    operations_mode = 'development'
    if options.version:
        operations_mode = 'production'
    version=options.version
    if not version:
        version='default'
    client.delete_service_version(service_id=options.service, service_version=version, mode=operations_mode)
    if operations_mode=='production':
        print 'Version [%s] of service [%s] has been deleted'%(options.service, options.version)
    else:
        print 'Development version of service [%s] has been deleted'%options.service
