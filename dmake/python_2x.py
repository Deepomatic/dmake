from StringIO import StringIO

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


def lru_cache(**kwargs):

    def decorator(target):
        # not implemented in python 2: use python3
        return target
    return decorator
