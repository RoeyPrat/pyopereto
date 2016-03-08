from pyopereto.client import OperetoClient
from optparse import OptionParser
import yaml

def parse_options():
    usage = "%prog -s service_name [-t title] [-a agent]"
    parser = OptionParser(usage=usage)
    parser.add_option("-s", "--service", dest="service", help="service name.")
    parser.add_option("-t", "--title", dest="title", help="process title (optional).")
    parser.add_option("-a", "--agent", dest="agent", default='any', help="agent name (optional), default is 'any'.")


if __name__ == "__main__":
    (options, args) = parse_options()
    with open('config.yaml', 'r') as f:
        config = yaml.load(f.read())
    print config
    client = OperetoClient(**config)
    client.create_process(service=options.service, title=options.title, agent=options.agent)

