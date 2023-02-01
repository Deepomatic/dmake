from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session
import requests

import argparse
import re
from requests.auth import HTTPBasicAuth

from dmake.common import DMakeException, logger
import dmake.docker_config as docker_config

from functools import lru_cache


REGISTRY_URL = 'https://registry-1.docker.io'


@lru_cache()
def create_authenticated_requests_session(registry_url, token_url, scope, service):
    """Performs docker registry authentication.

    Return: authenticated requests.Session
    """
    # https://docs.docker.com/registry/spec/auth/oauth/
    # In fact it's using the old authentication mode with a GET request for maximum registry compatiblity:
    # https://docs.docker.com/registry/spec/auth/token/
    # TODO: use oauth2 with POST request, then fallback to that GET request if 404.
    username, password = docker_config.get_auth_username_password(registry_url)
    client = OAuth2Session(client=BackendApplicationClient(client_id='dmake'))
    client.fetch_token(token_url=token_url,
                       method='GET',
                       auth=HTTPBasicAuth(username, password),
                       service=service, scope=str(scope))

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


@lru_cache()
def get_image_digest(image):
    """Get image digest (sha256)"""
    logger.debug('get_image_digest: %s', image)

    namespace, name, tag = parse_docker_image(image)

    # https://docs.docker.com/registry/spec/api/#pulling-an-image
    manifest_path = '/v2/%s/%s/manifests/%s' % (namespace, name, tag)
    accepted_content_types = [
        'application/vnd.oci.image.index.v1+json',
        'application/vnd.docker.distribution.manifest.v2+json'
    ]
    headers = {'Accept': ', '.join(accepted_content_types)}
    response = get(REGISTRY_URL, manifest_path, headers=headers)

    # https://docs.docker.com/registry/spec/api/#content-digests
    if response.status_code != 200 \
       or response.headers['content-type'] not in accepted_content_types \
       or 'Docker-Content-Digest' not in response.headers:
        raise DMakeException('Docker registry: Error getting image digest: %s%s %s %s %s' %
                             (REGISTRY_URL, manifest_path, response.headers, response.status_code, response.text))

    return response.headers['Docker-Content-Digest']


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=['image-digest'], default='image-digest', nargs='?', help="Command on docker registry")
    parser.add_argument("image", default='ubuntu:20.04', nargs='?', help="Docker image")
    args = parser.parse_args()

    if args.command == 'image-digest':
        digest = get_image_digest(args.image)
        print("Image digest: %s: %s" % (args.image, digest))
