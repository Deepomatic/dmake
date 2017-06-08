import os
import md5

from deepomatic.dmake.serializer import ValidationError
from deepomatic.dmake.common import DMakeException
from deepomatic.dmake.service import ExternalService, Service, ServiceManager
from deepomatic.dmake.action import Action

###############################################################################

class DMakeFileAbstract(object):
    serializer = None # Need to be defined
    _md5s = {}

    # At least those actions needs to be defined:
    class ShellCommand(Action):
        stage = 'command'
    class TestCommand(Action):
        stage = 'command'
    class DeployCommand(Action):
        stage = 'command'

    def __init__(self, service_managers, file, data):
        self._service_managers = service_managers
        self._file = file
        self._path = os.path.join(os.path.dirname(file), '')
        self._actions = {}

        self._register_action_(self.ShellCommand)
        self._register_action_(self.TestCommand)
        self._register_action_(self.DeployCommand)

        # Register dmake file hash
        count = 0
        while True:
            m = md5.new()
            m.update(str(count) + '@')
            m.update(self._path)
            m = m.hexdigest()
            if m not in self._md5s:
                self._md5s[m] = self
                self._md5 = m
                break
            count += 1

        # TODO
        if True:
        #try:
            self.serializer._validate_(self._path, data)
        # except ValidationError as e:
        #     raise DMakeException(("Error in %s:\n" % str(self)) + str(e))

        # Register declared services
        self.register_services()

    def __str__(self):
        return self._file

    def _register_service_(self, external, name, docker_image_name, dependencies = [], test_dependencies = []):
        app_name = self.get_app_name()
        if app_name not in self._service_managers:
            self._service_managers[app_name] = ServiceManager()
        service_manager = self._service_managers[app_name]

        if external:
            service_manager.add_service(ExternalService(self, name, docker_image_name))
        else:
            service_manager.add_service(Service(self, name, docker_image_name, dependencies, test_dependencies))

    def _register_action_(self, action_class):
        self._actions[action_class.__name__] = action_class

    def get_md5(self):
        return self._md5

    def get_path(self):
        return self._path

    def get_action(self, action_name):
        return self._actions[action_name]

    def get_app_name(self):
        """
        This MUST BE OVERLOADED and need to return the application name.
        """
        raise Exception("get_app_name() needs to be overloaded")

    def get_black_list(self):
        """
        This MUST BE OVERLOADED and need to return the application name.
        """
        raise Exception("get_black_list() needs to be overloaded")

    def register_services(self):
        """
        This MUST BE OVERLOADED and to use self._register_service_ on each service
        """
        raise Exception("register_services() needs to be overloaded")
