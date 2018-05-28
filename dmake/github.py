import os
import requests
import json
from dmake.common import DMakeException

host = 'https://api.github.com'


########## HELPERS ##########

def get_token():
    token = os.getenv('DMAKE_GITHUB_TOKEN', None)
    if token is None:
        raise DMakeException("Your need to define your Github Access Token by setting the DMAKE_GITHUB_TOKEN environment variable")
    return token


def check_status(r, msg_on_404=None, accept_codes=None):
    if msg_on_404 is None:
        msg_on_404 = "Resource not found: check the token's permissions"
    if accept_codes is None:
        accept_codes = [200, 201]
    if r.status_code == 401:
        raise DMakeException("Bad Github token: Access denied")
    if r.status_code == 404:
        raise DMakeException("Bad Github token: " + msg_on_404)
    if r.status_code not in accept_codes:
        raise DMakeException("Bad Github token: Got status code {}: {}".format(r.status_code, r.json()))


def get_helper(uri, msg_on_404=None, accept_codes=None):
    token = get_token()
    r = requests.get(host + uri, headers={'Authorization': 'token ' + token})
    check_status(r)
    return r.json()


def post_helper(uri, data, msg_on_404=None, accept_codes=None):
    token = get_token()
    r = requests.post(host + uri, headers={'Authorization': 'token ' + token}, data=json.dumps(data))
    check_status(r)
    return r.json()


########## API ##########

def check_token():
    user()


def user():
    return get_helper('/user')


def releases(owner, repo):
    return get_helper('/repos/{owner}/{repo}/releases'.format(owner=owner, repo=repo))

def create_releases(owner, repo, tag, branch, description, prerelease):
    data = {
        "tag_name": tag,
        "target_commitish": branch,
        "name": tag,
        "body": description,
        "draft": False,
        "prerelease": prerelease
    }
    return post_helper('/repos/{owner}/{repo}/releases'.format(owner=owner, repo=repo), data)

