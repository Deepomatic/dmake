
###############################################################################

class Action(object):
    """
    Class responsible for generating build commands
    """

    stage = None        # Needs to be defined
    use_service = True  # Can be set to False if the actions does not make use of the service
    args = []           # List of Action argument

    def __init__(self, action_manager, service, **kwargs):
        self._action_manager = action_manager
        self._depends        = []

        dmake_file = service.get_dmake_file()
        if self.use_service:
            self.__commands = self._generate_(dmake_file, service, **kwargs)
        else:
            self.__commands = self._generate_(dmake_file, None, **kwargs)

    @classmethod
    def get_key(cls, service, **kwargs):
        # Checks that kwargs is valid
        for a in cls.args:
            if a not in kwargs:
                raise Exception("ActionNode(%s): argument '%s' is requested" % (cls.__name__, a))
        for a in kwargs:
            if a not in cls.args:
                raise Exception("ActionNode(%s): argument '%s' is unexpected" % (cls.__name__, a))

        key = []
        if cls.use_service:
            key.append(service.get_name())
        else:
            key.append(None)

        for a in cls.args:
            val = kwargs[a]
            if isinstance(val, list):
                val = ','.join(val)
            elif isinstance(val, dict):
                val = ','.join(['%s:%s' % (str(k), str(v)) for (k,v) in val.items()])
            key.append('%s' % str(val))
        return tuple(key)

    def request(self, action_name, service_name, **kwargs):
        node = self.action_manager.request(action_name, service_name, **kwargs)
        self.depends.append(node)
        return node

    def _generate_(self, dmake_file, service, **kwargs):
        """
        This MUST BE OVERLOADED to generate a command list
        """
        raise Exception("_generate_() need to be defined")

###############################################################################

class ActionManager(object):

    def __init__(self, service_manager):
        self.__service_manager = service_manager
        self.__actions = {}

    def request(self, action_name, service_name, **kwargs):
        service = self.__service_manager.get_service(service_name)
        action_class = service.get_dmake_file().get_action(action_name)
        key = action_class.get_key(service, **kwargs)
        if not key in self.__actions:
            self.__actions[key] = action_class(self, service, **kwargs)
        return self.__actions[key]

###############################################################################

# class Base(ActionTemplate):
#     stage = 'base'
#     use_service = False

#     def generate_commands(self, file, service):
#         pass

# class BaseDocker(ActionTemplate)
#     stage = 'base'

#     def needs(self, file, service):
#         return [Base()]

# class BuildApp(ActionTemplate)
#     stage = 'build'
#     args  = ['context']

#     def needs(self, file, service):
#         return [BaseDocker()]

# class BuildDocker(ActionTemplate)
#     stage = 'docker'
#     args  = ['context']

#     def needs(self, file, service, context):
#         return [BuildApp(context)]

# class Run(ActionTemplate):
#     stage = 'run'
#     args  = ['context', 'env']

#     def needs(self, file, service, context, env):
#         needed = [BuildDocker(context)]
#         for s in service.get_dependencies():
#             needed.append(Run.create(file, s, 'prod', env))
#         return needed

# class Test(ActionTemplate):
#     stage = 'test'

#     def needs(self, file, service):
#         needed = [BuildDocker('test')]
#         for (s, e) in service.get_test_dependencies(env):
#             needed.append(Run.create(file, s, 'prod', e))
#         return needed

# class Deploy(ActionTemplate):
#     stage = 'deploy'

#     def needs(self, file, service):
#         return [Test()]

# ###############################################################################

# class ShellCommand(CommandTemplate):
#     stage = 'command'

#     def needs(self, file, service):
#         return [BuildDocker('test')]

# class DeployCommand(CommandTemplate):
#     stage = 'command'

#     def needs(self, file, service):
#         return [Deploy()]

# class TestCommand(CommandTemplate):
#     stage = 'command'

#     def needs(self, file, service):
#         return [Test()]
