from dmake.core import make


def entry_point(options):
    options.with_dependencies = True
    make(options)
