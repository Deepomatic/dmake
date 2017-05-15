from deepomatic.dmake.common import DMakeException


###############################################################################

class ActionContext(object):
    def __init__(self):
        self._fields = {}

    def __getattribute__(self, key):
        fields = object.__getattribute__(self, '_fields')
        if key in fields:
            return fields[key]
        else:
            return object.__getattribute__(self, key)

    def set(self, key, value):
        if key in self._fields:
            if value != self._fields[key]:
                raise Exception("Action nodes are over-writing context for key '%s' with different values. Value before: '%s', value after: '%s'." % (key, self._fields[key], value))
        else:
            self._fields[key] = value

    def items(self):
        return self._fields.items()

    def merge(self, context):
        for key, value in context.items():
            self.set(key, value)

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
        self._commands       = []
        self._depends        = []
        self._context        = ActionContext()

        dmake_file = service.get_dmake_file()
        if self.use_service:
            self._commands = self._generate_(dmake_file, service, **kwargs)
        else:
            self._commands = self._generate_(dmake_file, None, **kwargs)

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

    @property
    def context(self):
        return self._context

    def request(self, action_name, service, **kwargs):
        node = self._action_manager.request(action_name, service.get_name(), **kwargs)
        self._context.merge(node.context)
        self._depends.append(node)
        return node

    def append_command(self, cmd, **args):
        def check_cmd(args, required, optional = []):
            for a in required:
                if a not in args:
                    raise DMakeException("%s is required for command %s" % (a, cmd))
            for a in args:
                if a not in required and a not in optional:
                    raise DMakeException("Unexpected argument %s for command %s" % (a, cmd))
        if cmd == "stage":
            check_cmd(args, ['name', 'concurrency'])
        elif cmd == "sh":
            check_cmd(args, ['shell'])
        elif cmd == "read_sh":
            check_cmd(args, ['var', 'shell'], optional = ['fail_if_empty'])
            args['id'] = len(self._commands)
            if 'fail_if_empty' not in args:
                args['fail_if_empty'] = False
        elif cmd == "env":
            check_cmd(args, ['var', 'value'])
        elif cmd == "git_tag":
            check_cmd(args, ['tag'])
        elif cmd == "junit":
            check_cmd(args, ['report'])
        elif cmd == "cobertura":
            check_cmd(args, ['report'])
        elif cmd == "publishHTML":
            check_cmd(args, ['directory', 'index', 'title'])
        elif cmd == "build":
            check_cmd(args, ['job', 'parameters', 'propagate', 'wait'])
        else:
            raise DMakeException("Unknow command %s" %cmd)
        cmd = (cmd, args)
        self._commands.append(cmd)

    def dmake_shell_command(self, command, *args):
        return "%s %s" % (command, ' '.join(['"%s"' % a.replace('"', '\\"') for a in args]))

    def _generate_(self, dmake_file, service, **kwargs):
        """
        This MUST BE OVERLOADED to generate a command list
        """
        raise Exception("_generate_() need to be defined")

###############################################################################

class ActionManager(object):

    def __init__(self, service_manager):
        self._service_manager = service_manager
        self._actions = {}

    def request(self, action_name, service_name, **kwargs):
        service = self._service_manager.get_service(service_name)
        action_class = service.get_dmake_file().get_action(action_name)
        key = action_class.get_key(service, **kwargs)
        if not key in self._actions:
            self._actions[key] = action_class(self, service, **kwargs)
        return self._actions[key]

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
