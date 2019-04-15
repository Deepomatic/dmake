from io import StringIO
from abc import ABC, ABCMeta

from collections import OrderedDict

from functools import lru_cache

class MetaSerializerMixin(ABCMeta):
    @classmethod
    def __prepare__(metacls, name, bases, **kwargs):
        return OrderedDict()
    def __new__(cls, name, bases, namespace, **kwargs):
        result = ABCMeta.__new__(cls, name, bases, dict(namespace))
        ns = []
        for b in bases:
            if isinstance(b, MetaSerializerMixin):
                ns += b.__fields_order__
        result.__fields_order__ = tuple(ns) + tuple(namespace)
        return result

class SerializerMixin(ABC, metaclass=MetaSerializerMixin):
    pass

def is_string(x):
    return isinstance(x, str)

def to_string(x):
    return str(x)

def read_input(msg):
    return input(msg + ' ')

def subprocess_output_to_string(output):
    """Returns a python 3 string (unicode characters string) from a 'bytes' object"""
    return output.decode()
