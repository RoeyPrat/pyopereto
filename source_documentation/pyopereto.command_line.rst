.. pyopereto documentation master file, created by
   sphinx-quickstart on Thu Nov 15 09:39:45 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

``pyopereto.command_line`` Module
===========================


Usage:
  opereto sandbox list

  opereto sandbox purge

  opereto sandbox deploy <service-directory> [--service-name=NAME | --recursive] [--comment=COMMENT]

  opereto sandbox run <service-name> [--agent=AGENT] [--title=TITLE] [--params=JSON_PARAMS] [--async]

  opereto sandbox delete <service-name>

  opereto configure <service-directory>

  opereto services list [<search_pattern>]

  opereto services deploy <service-directory> [--service-version=VERSION] [--service-name=NAME | --recursive] [--comment=COMMENT]

  opereto services run <service-name> [--agent=AGENT] [--title=TITLE]  [--params=JSON_PARAMS] [--service-version=VERSION] [--async]

  opereto services delete <service-name> [--service-version=VERSION]

  opereto services info <service-name> [--service-version=VERSION]

  opereto versions <service-name>

  opereto process <pid> [--info] [--properties] [--log] [--rca] [--flow] [--all]

  opereto process rerun <pid> [--title=TITLE] [--agent=AGENT] [--async]

  opereto agents list [<search_pattern>]

  opereto environments list

  opereto environment <environment-name>

  opereto globals list [<search_pattern>]

  opereto (-h | --help)

  opereto --version

Options:
    search_pattern         : Textual search expression used to filter the search results. If more than one word, must enclose with double quotes.

    service-name           : The service identifier (e.g. my_service)

    service-directory      : Full path to your service directory

    service-version        : Version string (e.g. 1.2.0, my_version..)

    comment                : Service deployment comment that will appear in the service audit log

    title                  : The process headline enclosed with double quotes

    agent                  : The service identifier (e.g. my_test_agent)

    environment-name       : The environment identifier

    pid                    : The process identifier (e.g. 8XSVFdViKum)

    [--recursive]          : Recursively deploy all micro services found in a given directory

    [--async]              : Run the service asynchronously (returns only the service process id)

    [--params=JSON_PARAMS] : Initiated process input parameters. Must be a JSON string (e.g. --params='{"param1": "value", "param2": true, "param3": 100}')

    [--info]               : Prints process information

    [--properties]         : Prints process input and output properties

    [--log]                : Prints process execution log

    [--flow]               : Prints process flow near processes (ancestor and direct children)

    [--rca]                : Prints process root cause failure tree (e.g all child processes that caused the failure)

    [--all]                : Print all process data entities

    -h,--help              : Show this help message

    [--version]            : Show this tool version
