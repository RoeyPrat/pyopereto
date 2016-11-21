from client import OperetoClient, OperetoClientError
import traceback
import abc, sys
import types
import json


def _validate_list(var):
    return isinstance(var, types.ListType)

def _validate_dict(var):
    return isinstance(var, dict)

def _validate_string(var):
    return isinstance(var, basestring)

def _validate_boolean(var):
    return isinstance(var, bool)

def _validate_integer(var):
    if _validate_boolean(var):
        return False
    return isinstance(var, (int, long))

def _validate_json(var):
    try:
        json.dumps(var)
    except:
        return False


def _validate_type(key, value=None, type='string'):
    if value:

        valid_types = ['string', 'dict', 'list', 'json', 'integer', 'boolean']

        def _error(key, type):
            raise OperetoClientError('The value of input property [%s] must be of type [%s]'%(key, type))

        if type not in valid_types:
            raise OperetoClientError('Unknown type: %s. Valid types are: %s'%(type, str(valid_types)))

        _valid = {
            'string': _validate_string(value),
            'dict': _validate_dict(value),
            'list': _validate_list(value),
            'json': _validate_json(value),
            'integer': _validate_integer(value),
            'boolean': _validate_boolean(value),
        }
        _valid[type] or _error(key,type)


class ServiceTemplate(object):

    __metaclass__ = abc.ABCMeta

    def __init__(self, **kwargs):
        self.client = OperetoClient()
        self.input = self.client.input
        if kwargs:
            self.input.update(kwargs)

    def _validate(self, key, type=None, mandatory=False):
        if mandatory and not self.input.get(key):
            raise OperetoClientError('Mandatory input property [%s] does not have a value.'%key)
        if type:
            _validate_type(key, self.input.get(key), type)

    def _unimplemented_method(self):
        raise Exception, 'Unimplemented method'

    @abc.abstractmethod
    def setup(self):
        self._unimplemented_method()

    @abc.abstractmethod
    def process(self):
        self._unimplemented_method()

    @abc.abstractmethod
    def teardown(self):
        self._unimplemented_method()

    def run(self):
        try:
            self.setup()
            return self.process()
        except Exception,e:
            print >> sys.stderr, traceback.format_exc()
            raise Exception, 'Service execution failed.'
        finally:
            self.teardown()