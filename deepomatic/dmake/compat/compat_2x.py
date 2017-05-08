###############################################################################
##                                                                           ##
##                               common.py                                   ##
##                                                                           ##
###############################################################################

def is_string(x):
    return isinstance(x, basestring)

def read_input(msg):
    return raw_input(msg + ' ')

###############################################################################
##                                                                           ##
##                             serializer.py                                 ##
##                                                                           ##
###############################################################################

# Define the base class for YAML2PipelineSerializer
# If using Python3, we can keep track of the order of the field
# in order to generate a proper doc.

class BaseYAML2PipelineSerializer(object):
    pass
