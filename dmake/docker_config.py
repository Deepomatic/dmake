from dmake.common import DMakeException
import dmake.common as common

import base64
import json
import os

# python2 support
try:
    FileNotFoundError
except NameError:
    FileNotFoundError = IOError

def convert_to_hostname(url):
    """ConvertToHostname converts a registry url which has http|https prepended to just an hostname."""
    stripped = url
    if url.startswith('http://'):
        stripped = url[len('http://'):]
    elif url.startswith('https://'):
        stripped = url[len('https://'):]

    parts = stripped.split('/', 1)
    return parts[0]


def get_docker_config_auth(registry_url, dockercfg = '~/.docker/config.json'):
    """Parse docker config file.

    Return: registry authorization config.
    """
    # https://docs.docker.com/engine/reference/commandline/login/#privileged-user-requirement
    dockercfg = os.path.expanduser(dockercfg)
    try:
        with open(dockercfg, 'r') as f:
            cfg_data = json.load(f)
    except FileNotFoundError:
        raise common.DockerConfigFileNotFoundException(dockercfg)

    if 'credHelpers' in cfg_data:
        credentials_helpers = cfg_data['credHelpers']
        hostname = convert_to_hostname(registry_url)
        if hostname in credentials_helpers:
            credentials_store = credentials_helpers[hostname]
            # TODO FIX: probably won't work with registry = hostname
            return credentials_store, hostname, {}
        else:
            for registry, credentials_store in credentials_helpers.items():
                if registry.startswith(registry_url):
                    return credentials_store, registry, {}

    credentials_store = None
    if 'credsStore' in cfg_data:
        credentials_store = cfg_data['credsStore']

    for registry, registry_data in cfg_data['auths'].items():
        if registry.startswith(registry_url):
            return credentials_store, registry, registry_data

    if registry_url == 'https://registry-1.docker.io':
        # fallback to default v1 creds
        return get_docker_config_auth('https://index.docker.io', dockercfg)

    raise DMakeException('Auth not found for registry %s in docker config file %s' % (registry_url, dockercfg))


def docker_credentials_store(store, command, input):
    """Calls the docker credentials store with command and input.

    Return: parsed output
    """
    # https://docs.docker.com/engine/reference/commandline/login/#credentials-store
    output = common.run_shell_command('docker-credential-%s %s' % (store, command), stdin=input, raise_on_return_code=True)

    return json.loads(output)


def get_auth_username_password(registry_url):
    """Extracts docker registry auth from docker config file.

    Return: (username, password)
    """
    credentials_store, registry, data = get_docker_config_auth(registry_url)
    if credentials_store is None:
        # get from config file data
        auth = data['auth']
        username_password = base64.b64decode(auth).decode("UTF-8")
        return tuple(username_password.split(':', maxsplit=1))
    else:
        # get from credentials store
        data = docker_credentials_store(credentials_store, 'get', registry)
        return (data['Username'], data['Secret'])
