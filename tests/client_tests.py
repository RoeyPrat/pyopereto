import pytest
from pyopereto.client import OperetoClientError
import helpers.test_helper_methods as test_helper_methods
import os
import uuid
import tempfile

GENERIC_SERVICE_ID = 'a1234321'
GENERIC_AGENT_ID = 'xxxAgent'


class TestPyOperetoClient ():

    def setup(self):
        self.my_service = 'my_service_unittest'

    # Agent
    def test_create_agent_invalid_name(self, opereto_client):
        with pytest.raises (OperetoClientError) as opereto_client_error:
            result = opereto_client.create_agent (agent_id='ArielAgent')
        assert 'Invalid agent' in opereto_client_error.value.message

    def test_create_agent(self, opereto_client):
        result_data = opereto_client.create_agent (agent_id='xAgent', name='My new agent',
                                                   description='A new created agent to be called from X machines')
        assert result_data == 'xAgent'

        opereto_client.delete_agent (agent_id=result_data)

    # Opereto Server
    def test_hello(self, opereto_client):
        result_data = opereto_client.hello ();
        assert 'Hello, welcome to Opereto' in result_data

    # Services
    def test_search_services(self, opereto_client):
        test_helper_methods.zip_and_upload (opereto_client,
                                            os.path.abspath ('test_data/microservices/testing_hello_world'),
                                            service_id='testing_hello_world', mode='production', service_version='111')

        search_filter = {'generic': 'testing'}
        search_result = opereto_client.search_services (filter=search_filter)
        assert search_result is not None
        opereto_client.delete_service (GENERIC_SERVICE_ID)

        assert search_result is not None

    def test_get_service(self, opereto_client):
        test_helper_methods.zip_and_upload (opereto_client,
                                            os.path.abspath ('test_data/microservices/testing_hello_world'),
                                            service_id=GENERIC_SERVICE_ID, mode='production', service_version='111')

        service = opereto_client.get_service (GENERIC_SERVICE_ID)
        assert service['id'] == GENERIC_SERVICE_ID
        opereto_client.delete_service (GENERIC_SERVICE_ID)

    def test_get_service_version(self, opereto_client):
        test_helper_methods.zip_and_upload (opereto_client,
                                            os.path.abspath ('test_data/microservices/testing_hello_world'),
                                            service_id=GENERIC_SERVICE_ID, mode='production', service_version='111')

        service = opereto_client.get_service_version (GENERIC_SERVICE_ID, version='111')

        opereto_client.delete_service (GENERIC_SERVICE_ID)

        assert service['actual_version'] == '111'

    def test_validate_service(self, opereto_client):
        spec = {
            "type": "action",
            "cmd": "python -u run.py",
            "timeout": 600,
            "item_properties": [
                {"key": "key1", "type": "text", "value": "value1", "direction": "input"},
                {"key": "key2", "type": "boolean", "value": True, "direction": "input"}
            ]
        }
        assert opereto_client.verify_service ('hello_world', specification=spec)['errors'] == []

    def test_modify_service(self, opereto_client):
        test_helper_methods.zip_and_upload (opereto_client,
                                            os.path.abspath ('test_data/microservices/testing_hello_world'),
                                            service_id=GENERIC_SERVICE_ID, mode='production', service_version='111')

        service = opereto_client.modify_service (GENERIC_SERVICE_ID, 'container')
        assert service['type'] == 'container'

        opereto_client.delete_service (GENERIC_SERVICE_ID)

    def test_modify_service(self, opereto_client):
        assert self.my_service in opereto_client.modify_service (self.my_service, 'container')
        assert opereto_client.get_service (self.my_service)['type'] == 'container'
        assert self.my_service in opereto_client.modify_service (self.my_service, 'action')
        assert opereto_client.get_service (self.my_service)['type'] == 'action'

        opereto_client.delete_service (self.my_service)

    def test_upload_service_version(self, opereto_client):
        zip_action_file = test_helper_methods.zip_folder (
            os.path.join (os.path.dirname (__file__), 'test_data/microservices/testing_hello_world'))
        opereto_client.upload_service_version (service_zip_file=zip_action_file + '.zip', mode='production',
                                               service_version='111', service_id='testing_hello_world')
        assert '111' in opereto_client.get_service ('testing_hello_world', mode='production', version='111')['versions']
        opereto_client.delete_service_version (service_id='testing_hello_world', mode='production',
                                               service_version='111')
        assert '111' not in opereto_client.get_service ('hello_world')['versions']

    def test_delete_service_version(self, opereto_client):
        test_helper_methods.zip_and_upload (opereto_client,
                                            os.path.abspath ('test_data/microservices/testing_hello_world'),
                                            service_id=GENERIC_SERVICE_ID, mode='production', service_version='111')
        assert '111' in opereto_client.get_service ('testing_hello_world')['versions']
        opereto_client.delete_service_version (service_id='testing_hello_world', mode='production',
                                               service_version='111')
        assert '111' not in opereto_client.get_service ('testing_hello_world')['versions']

    def test_list_sandbox_services(self, opereto_client):
        test_helper_methods.zip_and_upload (opereto_client,
                                            os.path.abspath ('test_data/microservices/testing_hello_world'),
                                            service_id='testing_hello_world', mode='development', service_version='111')
        assert 'testing_hello_world' in opereto_client.list_development_sandbox ()
        opereto_client.delete_service ('testing_hello_world')
        assert 'testing_hello_world' not in opereto_client.list_development_sandbox ()

    def test_purge_develooment_sandbox(self, opereto_client):
        test_helper_methods.zip_and_upload (opereto_client,
                                            os.path.abspath ('test_data/microservices/testing_hello_world'),
                                            service_id='testing_hello_world', mode='development', service_version='111')
        assert 'testing_hello_world' in opereto_client.list_development_sandbox ()
        opereto_client.purge_development_sandbox ()
        assert 'testing_hello_world' not in opereto_client.list_development_sandbox ()

    # Agents

    def test_search_agents(self, opereto_client):
        opereto_client.create_agent (agent_id=GENERIC_AGENT_ID, name='My new agent',
                                     description='A new created agent to be called from X machines')
        search_filter = {'generic': 'My new'}
        search_result = opereto_client.search_agents (filter=search_filter)
        assert search_result is not None

        opereto_client.delete_agent (agent_id=GENERIC_AGENT_ID)

        assert search_result is not None

    def test_get_agent(self, opereto_client):
        opereto_client.create_agent (agent_id=GENERIC_AGENT_ID, name='My new agent',
                                     description='A new created agent to be called from X machines')
        assert opereto_client.get_agents (agent_id=GENERIC_AGENT_ID) is not None

        opereto_client.delete_agent (agent_id=GENERIC_AGENT_ID)

    def test_get_agent_properties(self, opereto_client):
        opereto_client.create_agent (agent_id=GENERIC_AGENT_ID, name='My new agent',
                                     description='A new created agent to be called from X machines')
        assert opereto_client.get_agent_properties (agent_id=GENERIC_AGENT_ID)['name'] == 'My new agent'

        opereto_client.delete_agent (agent_id=GENERIC_AGENT_ID)

    def test_modify_agent_property(self, opereto_client):
        opereto_client.create_agent (agent_id=GENERIC_AGENT_ID, name='My new agent',
                                     description='A new created agent to be called from X machines')
        assert opereto_client.get_agents (agent_id=GENERIC_AGENT_ID) is not None

        opereto_client.modify_agent_property (GENERIC_AGENT_ID, 'my_new_custom_property', 'my value')
        assert opereto_client.get_agent_properties (agent_id=GENERIC_AGENT_ID)['custom'][
                   'my_new_custom_property'] == 'my value'

        opereto_client.delete_agent (agent_id=GENERIC_AGENT_ID)

    def test_modify_agent_properties(self, opereto_client):
        opereto_client.create_agent (agent_id=GENERIC_AGENT_ID, name='My new agent',
                                     description='A new created agent to be called from X machines')
        assert opereto_client.get_agents (agent_id=GENERIC_AGENT_ID) is not None

        properties_key_value = {"mykey": "my value"}
        opereto_client.modify_agent_properties (GENERIC_AGENT_ID, properties_key_value)
        agent_properties = opereto_client.get_agent_properties (agent_id=GENERIC_AGENT_ID)
        assert opereto_client.get_agent_properties (agent_id=GENERIC_AGENT_ID)['custom']['mykey'] == 'my value'
        opereto_client.delete_agent (agent_id=GENERIC_AGENT_ID)

    def test_modify_agent(self, opereto_client):
        opereto_client.create_agent (agent_id=GENERIC_AGENT_ID, name='My new agent',
                                     description='A new created agent to be called from X machines')
        assert opereto_client.get_agents (agent_id=GENERIC_AGENT_ID) is not None

        opereto_client.modify_agent (GENERIC_AGENT_ID, name="My new name")
        assert opereto_client.get_agent (agent_id=GENERIC_AGENT_ID)['name'] == 'My new name'
        opereto_client.delete_agent (agent_id=GENERIC_AGENT_ID)

    def test_get_agent_status(self, opereto_client):
        opereto_client.create_agent (agent_id=GENERIC_AGENT_ID, name='My new agent',
                                     description='A new created agent to be called from X machines')
        assert opereto_client.get_agent_status (agent_id=GENERIC_AGENT_ID)['online'] == False
        opereto_client.delete_agent (agent_id=GENERIC_AGENT_ID)

    def test_delete_agent(self, opereto_client):
        opereto_client.create_agent (agent_id=GENERIC_AGENT_ID, name='My new agent',
                                     description='A new created agent to be called from X machines')
        assert opereto_client.get_agents (agent_id=GENERIC_AGENT_ID) is not None

        opereto_client.delete_agent (agent_id=GENERIC_AGENT_ID)

        with pytest.raises (OperetoClientError) as operetoClientError:
            opereto_client.get_agents (agent_id=GENERIC_AGENT_ID)
        assert 'Entity type [agents] with id [' + GENERIC_AGENT_ID + '] not found' in operetoClientError.value.message

    def test_create_process(self, opereto_client):
        test_helper_methods.zip_and_upload (opereto_client,
                                            os.path.abspath ('test_data/microservices/testing_hello_world'),
                                            service_id='testing_hello_world', mode='production',
                                            service_version='default')

        process_properties = {"my_input_param": "Hello World"}

        pid = opereto_client.create_process (service='qwe', title='Testing...',
                                             agent=opereto_client.input['opereto_agent'], **process_properties)

        opereto_client.wait_for ([pid])
        opereto_client.delete_service ('testing_hello_world')

    def test_rerun_process(self, opereto_client):
        test_helper_methods.zip_and_upload (opereto_client,
                                            os.path.abspath ('test_data/microservices/testing_hello_world'),
                                            service_id='testing_hello_world', mode='production',
                                            service_version='default')

        process_properties = {"my_input_param": "Hello World"}

        pid = opereto_client.create_process (service='qwe', title='Testing...',
                                             agent=opereto_client.input['opereto_agent'], **process_properties)
        assert pid is not None
        opereto_client.wait_for ([pid])
        pid = opereto_client.rerun_process(pid)
        assert pid is not None
        opereto_client.delete_service ('testing_hello_world')
        assert pid is not None

    def test_modify_process_properties(self, opereto_client):
        test_helper_methods.zip_and_upload (opereto_client,
                                            os.path.abspath ('test_data/microservices/testing_hello_world'),
                                            service_id='testing_hello_world', mode='production',
                                            service_version='default')

        process_properties = {"my_input_param": "Hello World"}

        pid = opereto_client.create_process (service='qwe', title='Testing...',
                                             agent=opereto_client.input['opereto_agent'], **process_properties)
        assert pid is not None

        process_output_properties = {'my_output_param_2' : 'out param value'}
        opereto_client.modify_process_properties(process_output_properties, pid)
        opereto_client.wait_for([pid])
        process_output_property_value = opereto_client.get_process_property(pid, 'my_output_param_2')
        assert process_output_property_value == 'out param value'
        opereto_client.delete_service ('testing_hello_world')

    def test_modify_process_property(self, opereto_client):
        test_helper_methods.zip_and_upload (opereto_client,
                                            os.path.abspath ('test_data/microservices/testing_hello_world'),
                                            service_id='testing_hello_world', mode='production',
                                            service_version='default')

        process_properties = {"my_input_param": "Hello World"}

        pid = opereto_client.create_process (service='qwe', title='Testing...',
                                             agent=opereto_client.input['opereto_agent'], **process_properties)
        assert pid is not None

        opereto_client.modify_process_property('my_output_param_2', 'out param value', pid)
        opereto_client.wait_for([pid])
        process_output_property_value = opereto_client.get_process_property(pid, 'my_output_param_2')
        assert process_output_property_value == 'out param value'
        opereto_client.delete_service ('testing_hello_world')

    def test_stop_process(self, opereto_client):
        test_helper_methods.zip_and_upload (opereto_client,
                                            os.path.abspath ('test_data/microservices/testing_hello_world'),
                                            service_id='testing_hello_world', mode='production',
                                            service_version='default')

        process_properties = {"my_input_param": "Hello World"}

        pid = opereto_client.create_process(service='testing_hello_world', title='Testing...',
                                             agent=opereto_client.input['opereto_agent'], **process_properties)
        assert pid is not None
        opereto_client.stop_process(pid, "warning")
        status = opereto_client.get_process_status(pid)
        assert status == "warning"

def teardown(self):
    pass
