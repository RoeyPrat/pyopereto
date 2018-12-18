import pytest
from pyopereto.client import OperetoClientError
import test_helper_methods.test_helper_methods as test_helper_methods
import os
import uuid
import tempfile

GENERIC_SERVICE_ID = 'a1234321'


class TestPyOperetoClient():

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

        test_helper_methods.zip_and_upload(opereto_client, os.path.abspath('test_data/microservices/testing_hello_world'),
                                           service_id='testing_hello_world', mode='production', service_version='111')

        search_filter = {'generic': 'testing'}
        search_result = opereto_client.search_services(filter=search_filter)

        #opereto_client.delete_service(GENERIC_SERVICE_ID)

        assert search_result is not None

    def test_get_service(self, opereto_client):
        test_helper_methods.zip_and_upload (opereto_client,
                                            os.path.abspath ('test_data/microservices/testing_hello_world'),
                                            service_id=GENERIC_SERVICE_ID, mode='production', service_version='111')

        service = opereto_client.get_service(GENERIC_SERVICE_ID)

        opereto_client.delete_service(GENERIC_SERVICE_ID)

        assert service['id'] == GENERIC_SERVICE_ID

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

        opereto_client.delete_service(GENERIC_SERVICE_ID)

    def test_modify_service(self, opereto_client):
        assert self.my_service in opereto_client.modify_service(self.my_service, 'container')
        assert opereto_client.get_service(self.my_service)['type']=='container'
        assert self.my_service in opereto_client.modify_service(self.my_service, 'action')
        assert opereto_client.get_service(self.my_service)['type']=='action'

        opereto_client.delete_service(self.my_service)

    def test_upload_service_version(self, opereto_client):
        zip_action_file = test_helper_methods.zip_folder (os.path.join (os.path.dirname (__file__), 'test_data/microservices/testing_hello_world'))
        opereto_client.upload_service_version (service_zip_file=zip_action_file + '.zip', mode='production',
                                               service_version='111', service_id='testing_hello_world')
        assert '111' in opereto_client.get_service ('testing_hello_world', mode='production', version='111')['versions']
        opereto_client.delete_service_version (service_id='testing_hello_world', mode='production', service_version='111')
        assert '111' not in opereto_client.get_service ('hello_world')['versions']

    def test_delete_service_version(self, opereto_client):
        test_helper_methods.zip_and_upload (opereto_client,
                                            os.path.abspath ('test_data/microservices/testing_hello_world'),
                                            service_id=GENERIC_SERVICE_ID, mode='production', service_version='111')
        assert '111' in opereto_client.get_service ('testing_hello_world')['versions']
        opereto_client.delete_service_version (service_id='testing_hello_world', mode='production', service_version='111')
        assert '111' not in opereto_client.get_service ('testing_hello_world')['versions']

    def teardown(self):
        pass
