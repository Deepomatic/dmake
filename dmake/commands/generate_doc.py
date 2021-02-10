def entry_point(options):
    # lazy load for faster cli
    from dmake import docs

    kind = getattr(options, 'kind')
    if kind == 'usage':
        docs.usage()
    elif kind == 'format':
        docs.generate()
    elif kind == 'example':
        docs.example()
