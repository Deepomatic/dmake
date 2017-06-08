import sys

if sys.version_info >= (3,0):
    from deepomatic.dmake.compat.compat_3x import *
else:
    from deepomatic.dmake.compat.compat_2x import *