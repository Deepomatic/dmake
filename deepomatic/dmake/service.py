import deepomatic.dmake.common as common

###############################################################################

class ExternalService(object):
    """
    This class represents an external service object
    """

    def __init__(self, dmake_file, name, docker_image_name_tag):
        """
        dmake_file: file where the service has been defined
        name: the service name
        docker_full_image: Docker image name and tag
        """
        self._dmake_file = dmake_file
        self._name = name
        self._docker_image_name_tag = docker_image_name_tag

    @staticmethod
    def is_external():
        return True

    def get_dmake_file(self):
        return self._dmake_file

    def get_name(self):
        return self._name

    def get_docker_image_name_tag(self):
        return self._docker_image_name_tag

###############################################################################

class Service(ExternalService):
    """
    This class represents a service object that needs to be built
    """

    def __init__(self, dmake_file, name, docker_image_name, dependencies, test_dependencies):
        """
        dmake_file: file where the service has been defined
        name: the service name
        docker_image_name: Docker image name (without tag)
        dependencies: list of service names
        test_dependencies: list of tuples (service, env).
        """
        super(Service, self).__init__(dmake_file, name, docker_image_name + ':' + common.commit_id if docker_image_name else None)

        self._docker_image_name = docker_image_name
        self._dependencies = dependencies
        self._test_dependencies = test_dependencies

    @staticmethod
    def is_external():
        return False

    def get_docker_image_name(self):
        return self._docker_image_name

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
            raise common.DMakeException("Cannot find service '%s'" % service_name)

    def add_service(self, service):
        service_name = service.get_name()
        if service_name in self._services:
            raise common.DMakeException("Duplicate service '%s'" % service_name)
        else:
            self._services[service_name] = service
