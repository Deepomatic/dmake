###############################################################################
##                                                                           ##
##                               common.py                                   ##
##                                                                           ##
###############################################################################

def is_string(x):
    return isinstance(x, str)

def read_input(msg):
    return input(msg + ' ')

###############################################################################
##                                                                           ##
##                             serializer.py                                 ##
##                                                                           ##
###############################################################################

# Define the base class for YAML2PipelineSerializer
# If using Python3, we can keep track of the order of the field
# in order to generate a proper doc.

class MetaYAML2PipelineSerialize(type):
    @classmethod
    def __prepare__(metacls, name, bases, **kwargs):
        return OrderedDict()
    def __new__(cls, name, bases, namespace, **kwargs):
        result = type.__new__(cls, name, bases, dict(namespace))
        ns = []
        for b in bases:
            if isinstance(b, MetaYAML2PipelineSerialize):
                ns += b.__fields_order__
        result.__fields_order__ = tuple(ns) + tuple(namespace)
        return result

class BaseYAML2PipelineSerializer(object, metaclass = MetaYAML2PipelineSerialize):
    pass