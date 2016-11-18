class BaseYAML2PipelineSerializer(object):
    pass

def is_string(x):
    return isinstance(x, basestring)

def read_input(msg):
    return raw_input(msg + ' ')