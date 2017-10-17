from oauthlib.oauth2 import LegacyApplicationClient
from requests_oauthlib import OAuth2Session
import requests

import argparse
import json
import os
import re

from deepomatic.dmake.common import DMakeException


REGISTRY_URL = 'https://index.docker.io'


def get_auth_headers(registry_url, dockercfg = '~/.docker/config.json'):
    """Extracts docker registry auth from docker config file.

    Return: authorization headers
    """
    # https://docs.docker.com/engine/reference/commandline/login/#privileged-user-requirement
    dockercfg = os.path.expanduser(dockercfg)
    with open(dockercfg, 'r') as f:
        data = json.load(f)
    for registry, value in data['auths'].items():
        if registry.startswith(registry_url):
            auth = value['auth']
            break
    else:
        raise DMakeException('Auth not found for registry %s in docker config file %s' % (registry_url, dockercfg))

    return {'Authorization': 'Basic %s' % auth}


def create_authenticated_requests_session(registry_url, token_url, scope, service):
    """Performs docker registry authentication.

    Return: authenticated requests.Session
    """

    # https://docs.docker.com/registry/spec/auth/oauth/
    auth_headers = get_auth_headers(registry_url)
    client = OAuth2Session(client=LegacyApplicationClient(client_id='dmake'))
    client.fetch_token(token_url=token_url, headers=auth_headers, method='GET', service=service, scope=unicode(scope))

    return client


def get(registry_url, path, **kwargs):
    """Get a docker registry url, handling authentication

    Return: requests.Response
    """
    url = registry_url + path
    response = requests.get(url, **kwargs)

    # https://docs.docker.com/registry/spec/auth/token/
    # Www-Authenticate: Bearer realm="https://auth.docker.io/token",service="registry.docker.io",scope="repository:library/ubuntu:pull"
    if response.status_code != 401 or ("Www-Authenticate" not in response.headers):
        return response

    challenge = response.headers["Www-Authenticate"]
    regexp = '^Bearer\s+realm="(.+?)",service="(.+?)",scope="(.+?)",?'
    match = re.match(regexp, challenge)

    if not match:
        raise DMakeException('Docker registry: Unknown Www-Authenticate challenge')

    realm = match.group(1)
    service = match.group(2)
    scope = match.group(3)

    docker_registry_client = create_authenticated_requests_session(registry_url, scope=scope, service=service, token_url=realm)
    response = docker_registry_client.get(url, **kwargs)

    return response


def parse_docker_image(image):
    """Parse docker image, add defaults, return components."""
    # add defaults
    if '/' not in image:
        image = 'library/' + image
    if ':' not in image:
        image = image + ':latest'

    # parse
    tokens1 = image.split('/')
    namespace = tokens1[0]

    tokens2 = tokens1[1].split(':')
    name = tokens2[0]
    tag = tokens2[1]

    return namespace, name, tag

def get_image_digest(image):
    """Get image digest (sha256)"""
    namespace, name, tag = parse_docker_image(image)

    # https://docs.docker.com/registry/spec/api/#pulling-an-image
    manifest_path = '/v2/%s/%s/manifests/%s' % (namespace, name, tag)
    headers = {'Accept': 'application/vnd.docker.distribution.manifest.v2+json'}
    response = get(REGISTRY_URL, manifest_path, headers=headers)

    # https://docs.docker.com/registry/spec/api/#content-digests
    if response.status_code != 200 or 'Docker-Content-Digest' not in response.headers:
        raise DMakeException('Docker registry: Error getting image digest: %s %s' % (response.status_code, response.text))

    return response.headers['Docker-Content-Digest']


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=['image-digest'], default='image-digest', nargs='?', help="Command on docker registry")
    parser.add_argument("image", default='ubuntu:16.04', nargs='?', help="Docker image")
    args = parser.parse_args()

    if args.command == 'image-digest':
        digest = get_image_digest(args.image)
        print("Image digest: %s: %s" % (args.image, digest))
