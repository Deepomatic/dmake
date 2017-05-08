from deepomatic.dmake.common import DMakeException

###############################################################################

class Service(object):
    """
    This class represents a service object
    """

    def __init__(self, dmake_file, name, dependencies, test_dependencies):
        """
        name: the service name
        dependencies: list of service names
        test_dependencies: list of tuples (service, env).
        Services must be specified by their name, without application name.
        """
        self._dmake_file = dmake_file
        self._name = name
        self._dependencies = dependencies
        self._test_dependencies = test_dependencies

    def get_dmake_file(self):
        return self._dmake_file

    def get_name(self):
        return self._name

    def get_dependencies(self):
        return self._dependencies

    def get_test_dependencies(self):
        return self._test_dependencies

###############################################################################

class ServiceManager(object):
    """
    This class gathers services declared in an app
    """

    def __init__(self):
        self._services = {}

    def get_services(self):
        return self._services

    def get_service(self, service_name):
        if service_name in self._services:
            return self._services[service_name]
        else:
            raise DMakeException("Cannot find service '%s'" % service_name)

    def add_service(self, service):
        service_name = service.get_name()
        if service_name in self._services:
            raise DMakeException("Duplicate service '%s'" % service_name)
        else:
            self._services[service_name] = service
