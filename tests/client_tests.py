import pytest
from pyopereto.client import OperetoClientError
import test_helper_methods.test_helper_methods as test_helper_methods
import os
import uuid
import tempfile


class TestPyOperetoClient():

    # Agent
    def test_create_agent_invalid_name(self, opereto_client):
        with pytest.raises (OperetoClientError) as opereto_client_error:
            result = opereto_client.create_agent(agent_id='ArielAgent')
        assert 'Invalid agent' in opereto_client_error.value.message

    def test_create_agent(self, opereto_client):
        result_data = opereto_client.create_agent(agent_id='xAgent', name='My new agent', description='A new created agent to be called from X machines')
        assert result_data == 'xAgent'

        opereto_client.delete_agent(agent_id=result_data)

    # Opereto Server
    def test_hello(self, opereto_client):
        result_data = opereto_client.hello();
        assert 'Hello, welcome to Opereto' in result_data

    # Services
    def test_search_services(self, opereto_client):

        zip_action_file = os.path.join (tempfile.gettempdir(), str (uuid.uuid4 ()) + '.action')
        test_helper_methods.zipfolder (zip_action_file,
                                       os.path.join (os.path.dirname (__file__), 'test_data/microservices/testing_hello_world'))
        service_id = 'a1234321'
        opereto_client.upload_service_version (service_zip_file=zip_action_file + '.zip', mode='production',
                                               service_version='111', service_id=service_id)

        filter = {'generic': 'testing_'}
        search_result = opereto_client.search_services(filter=filter)

        opereto_client.delete_service (service_id)

        assert search_result is not None

    def teardown(self):
        pass


