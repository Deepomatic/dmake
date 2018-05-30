from dmake.core import make


def entry_point(options):
    options.dependencies = True
    make(options)
