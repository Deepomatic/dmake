def get_key(data, keys, default=None):
    keys = keys.split('.')
    try:
        for k in keys:
            data = data[k]
        return data
    except KeyError:
        return default

def delete_key(data, keys):
    keys = keys.split('.')
    for k in keys[:-1]:
        data = data[k]
    del data[keys[-1]]

def patch(data):
    for s in get_key(data, 'services', []):
        links = get_key(s, 'tests.docker_links_names')
        if links is not None:
            s['needed_links'] = links
            delete_key(s, 'tests.docker_links_names')
    return data
