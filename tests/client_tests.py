import pytest
from pyopereto.client import OperetoClientError
import test_helper_methods.test_helper_methods as test_helper_methods
import os
import uuid
import tempfile


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
        zip_action_file = os.path.join (tempfile.gettempdir (), str (uuid.uuid4 ()) + '.action')
        test_helper_methods.zipfolder (zip_action_file,
                                       os.path.join (os.path.dirname (__file__),
                                                     'test_data/microservices/testing_hello_world'))
        service_id = 'a1234321'
        opereto_client.upload_service_version (service_zip_file=zip_action_file + '.zip', mode='production',
                                               service_version='111', service_id=service_id)

        filter = {'generic': 'testing_'}
        search_result = opereto_client.search_services (filter=filter)

        opereto_client.delete_service (service_id)

        assert search_result is not None

    def test_get_service(self, opereto_client):
        zip_action_file = os.path.join (tempfile.gettempdir (), str (uuid.uuid4 ()) + '.action')
        test_helper_methods.zipfolder (zip_action_file,
                                       os.path.join (os.path.dirname (__file__),
                                                     'test_data/microservices/testing_hello_world'))
        service_id = 'a1234321'
        opereto_client.upload_service_version (service_zip_file=zip_action_file + '.zip', mode='production',
                                               service_version='111', service_id=service_id)

        service = opereto_client.get_service (service_id)

        opereto_client.delete_service (service_id)

        assert service['id'] == service_id

    def test_get_service_version(self, opereto_client):
        zip_action_file = os.path.join (tempfile.gettempdir (), str (uuid.uuid4 ()) + '.action')
        test_helper_methods.zipfolder (zip_action_file,
                                       os.path.join (os.path.dirname (__file__),
                                                     'test_data/microservices/testing_hello_world'))
        service_id = 'a1234321'
        opereto_client.upload_service_version (service_zip_file=zip_action_file + '.zip', mode='production',
                                               service_version='111', service_id=service_id)

        service = opereto_client.get_service_version (service_id, version='111')

        opereto_client.delete_service (service_id)

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
        zip_action_file = os.path.join (tempfile.gettempdir (), str (uuid.uuid4 ()) + '.action')
        test_helper_methods.zipfolder (zip_action_file,
                                       os.path.join (os.path.dirname (__file__),
                                                     'test_data/microservices/testing_hello_world'))
        service_id = 'a1234321'
        opereto_client.upload_service_version (service_zip_file=zip_action_file + '.zip', mode='production',
                                               service_version='111', service_id=service_id)

        service = opereto_client.modify_service (service_id, 'container')
        assert service['type'] == 'container'

        opereto_client.delete_service(service_id)

    def test_modify_service(self, opereto_client):
        assert self.my_service in opereto_client.modify_service(self.my_service, 'container')
        assert opereto_client.get_service(self.my_service)['type']=='container'
        assert self.my_service in opereto_client.modify_service(self.my_service, 'action')
        assert opereto_client.get_service(self.my_service)['type']=='action'

        opereto_client.delete_service(self.my_service)


    def teardown(self):
        pass
