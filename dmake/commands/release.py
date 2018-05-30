import os
import re
import dmake.common as common
import inquirer
from github import Github

from dmake.common import DMakeException


release_re = re.compile(r'v(\d+)\.(\d+)(?:\.(\d+))?(?:-rc\.(\d+))?')


def tag_to_key(tag):
    match = release_re.match(tag)
    if match is None:
        return None
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3)) if match.group(3) is not None else None
    rc    = int(match.group(4)) if match.group(4) is not None else None
    return (major, minor, patch, rc)


def key_to_tag(key):
    tag = "v{}.{}".format(key[0], key[1])
    if key[2] is not None:
        tag += '.{}'.format(key[2])
    if key[3] is not None:
        tag += '-rc.{}'.format(key[3])
    return tag


def entry_point(options):
    app = getattr(options, 'app')
    branch = options.branch

    token = os.getenv('DMAKE_GITHUB_TOKEN', None)
    owner = os.getenv('DMAKE_GITHUB_OWNER', None)
    if token is None:
        raise DMakeException("Your need to define your Github Access Token by setting the DMAKE_GITHUB_TOKEN environment variable")
    if owner is None:
        raise DMakeException("Your need to define your Github account/organization name by setting the DMAKE_GITHUB_OWNER environment variable")

    # Acces Github repo
    g = Github(token)
    owner = g.get_user(owner)
    repo = owner.get_repo(app)

    # List releases
    release_list = {}
    for release in repo.get_releases():
        key = tag_to_key(release.tag_name)
        if key is not None:
            release_list[key] = release
    sorted_release_keys = sorted(release_list.keys(), reverse=True)
    latest_per_major_minor = {}
    for key in sorted_release_keys:
        major, minor, patch, rc = key
        if (major, minor) not in latest_per_major_minor:
            latest_per_major_minor[(major, minor)] = key

    # Ask for previous version
    questions = [
        inquirer.List(
            'prev',
            message="Which was the previously released version?",
            choices=[release_list[key].tag_name for key in sorted_release_keys if key[0:2] in latest_per_major_minor and latest_per_major_minor[key[0:2]] == key] + ['Other'],
        ),
    ]
    answers = inquirer.prompt(questions)
    if answers['prev'] == 'Other':
        questions = [
            inquirer.List(
                'prev',
                message="Which was the previously released version?",
                choices=[release_list[key].tag_name for key in sorted_release_keys],
                carousel=True
            ),
        ]
        answers = inquirer.prompt(questions)
    prev_version = answers['prev']

    # Ask for next version
    key = tag_to_key(prev_version)
    next_tag = [
        (key[0], key[1] + 1, 0 if key[2] is not None else None, None),
        (key[0] + 1, 0, 0 if key[2] is not None else None, None)
    ]
    if key[2] is not None:
        next_tag.insert(0, (key[0], key[1], key[2] + 1, None))
    first = next_tag[0]
    next_tag.insert(len(next_tag), (first[0], first[1], first[2], first[3] + 1 if first[3] is not None else 1))

    questions = [
        inquirer.List(
            'next',
            message="Which will be the next version?",
            choices=[key_to_tag(tag) for tag in next_tag],
        ),
    ]
    next_version = inquirer.prompt(questions)['next']
    prerelease = tag_to_key(next_version)[3] is not None

    # Compute change log
    # TODO: use https://github.com/vaab/gitchangelog
    common.run_shell_command("git fetch --tags --quiet")
    change_log_cmd = "git log {prev}...deployed_version_{branch} --pretty=%s".format(prev=prev_version, branch=branch)
    change_log = common.run_shell_command(change_log_cmd)

    if change_log == "":
        print("No changes found. Exiting...")
        return

    # Recap
    questions = [
        inquirer.List(
            'choice',
            message="We will create a release tagged {tag} from branch '{branch}'".format(tag=next_version, branch=branch),
            choices=['Yes', 'No'],
        ),
    ]
    answers = inquirer.prompt(questions)
    if answers['choice'] == 'No':
        print('Aborting...')
        return

    # Creates the release
    repo.create_git_release(next_version, next_version, change_log, prerelease=prerelease)
    print("Done ! Check it at: https://github.com/{owner}/{repo}/releases/tag/{tag}".format(owner=owner.name, repo=repo.name, tag=next_version))
