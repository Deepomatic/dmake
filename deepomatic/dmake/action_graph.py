class ActionNode(object):
    def __init__(self):
        pass

###############################################################################

class ActionTemplate(object):
    """
        name: name of the action
        service_needed: boolean: specifies if the action needs a service
        actions_needed: actions it depends of
        variables_needed: the build variables needed by the action
        variables_provided: the build variables provided by the action
    """
    def __init__(self,
                 name,
                 node_class,
                 service_needed = False,
                 actions_needed = [],
                 variables_needed = [],
                 variables_provided = []):
        self.name = name
        self.node_class = node_class
        self.service_needed = service_needed
        self.actions_needed = actions_needed
        self.variables_needed = variables_needed
        self.variables_provided = variables_provided

    def create_node(self, action_manager, file, service):
        # Check if a service is provided if needed
        if self.service_needed:
            if service is None:
                raise Exception("Action '%s' needs a service to be specified" % self.name)
        else:
            service = None

        parents = []
        provided_variables = {}
        for action in self.actions_needed:
            node = action_manager.create_action_node(action, file, service)
            parents.append(node)
            for v in node._provided_variables_list_:
                if v in provided_variables:
                    raise Exception("Variable 'v' was declared by action '%s' but re-declared by action '%s'" % (provided_variables[v], action))
                provided_variables[v] = action

        # Check that needed variables are declared
        for v in self.variables_needed:
            if v not in provided_variables:
                raise Exception("Variable 'v' was not declared by parent actions of action '%s'" % self.name)

        # Update the list of provided variables
        for v in self.variables_provided:
            provided_variables[v] = self.name

        return self.node_class(parents, provided_variables.keys())


###############################################################################

class ActionManager(object):
    def __init__(self):
        self.action_templates = {}
        self.action_nodes = {}

    """
        name: name of the action
        dependancies: actions it depends of
        need_service: boolean: specifies if the action needs a service
        provides: the build variables provides by the action
    """
    def register_action(self, name, node_class, *args, **kwargs):
        self.action_templates[name] = ActionTemplate(name, node_class, *args, **kwargs)

    """
    """
    def new_action_node(self, action, file, service = None):
        if action not in self.actions:
            raise Exception("Un-registered action: '%s'" % action)

        key = (action, file, service)
        if key not in self.action_nodes:
            return self.action_nodes[key]

        node = self.action_templates[action].create_action_node(self, file, service)
        self.action_nodes[key] = node

        return node
