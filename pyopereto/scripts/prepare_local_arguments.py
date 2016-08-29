#!/usr/bin/python
from optparse import OptionParser
import os
import yaml
import json

TEMP_DIR = '/tmp'

def parse_options():
    usage = "%prog -d path/to/service/directory"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--dir", dest="dir", help="path to the service directory.")

    (options, args) = parser.parse_args()
    if not options.dir:
        parser.error('service directory must be provided.')
    return (options, args)



def create_argument_files(service_dir):
    with open(os.path.join(service_dir, 'service.yaml'), 'r') as f:
        spec = yaml.load(f.read())
    if spec['type'] in ['cycle', 'container']:
        raise Exception, 'Execution of service type [%s] in local mode is not supported.'%spec['type']
    service_cmd = spec['cmd']
    with open('arguments.yaml', 'r') as arguments_file:
        arguments_json = yaml.load(arguments_file.read())
    if spec.get('item_properties'):
        for item in spec['item_properties']:
            arguments_json[item['key']]=item['value']
    with open(os.path.join(service_dir, 'arguments.json'), 'w') as json_arguments_outfile:
        json.dump(arguments_json, json_arguments_outfile, indent=4, sort_keys=True)

    with open(os.path.join(service_dir, 'arguments.yaml'), 'w') as yaml_arguments_outfile:
        yaml.dump(yaml.load(json.dumps(arguments_json)), yaml_arguments_outfile, indent=4, default_flow_style=False)

    return service_cmd


if __name__ == "__main__":
    (options, args) = parse_options()
    print '-----------------------------------------------------------------------------'
    print '  Preparing local argument files (not including builtin opereto parameters.  '
    print '-----------------------------------------------------------------------------'
    cmd = create_argument_files(options.dir)

