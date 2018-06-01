from StringIO import StringIO  # noqa: F401


class BaseYAML2PipelineSerializer(object):
    pass

def is_string(x):
    return isinstance(x, basestring)

def to_string(x):
    return unicode(x)

def read_input(msg):
    return raw_input(msg + ' ')

def subprocess_output_to_string(output):
    """Returns a python 2 str (bytes characters string)"""
    return output

