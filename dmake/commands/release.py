import os
import dmake.common as common
import inquirer
import semver
from github import Github

from dmake.common import DMakeException


def remove_tag_prefix(tag):
    return tag[1:] if tag.startswith('v') else tag


def tag_to_key(tag):
    try:
        return semver.parse_version_info(remove_tag_prefix(tag))
    except ValueError:
        return None


def entry_point(options):
    app = getattr(options, 'app')
    release_tag = getattr(options, 'tag')

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
    tags_list = {}
    for tag in repo.get_tags():
        key = tag_to_key(tag.name)
        if key is not None:
            tags_list[key] = tag
    sorted_release_keys = sorted(tags_list.keys(), reverse=True)
    latest_per_major_minor = {}
    for key in sorted_release_keys:
        if (key.major, key.minor) not in latest_per_major_minor:
            latest_per_major_minor[(key.major, key.minor)] = key

    # Ask for previous version
    if release_tag is None:
        questions = [
            inquirer.List(
                'release_tag',
                message="Here are only the latest tags per minor version. Which tag do you want to release?",
                choices=[tags_list[key].name for key in sorted_release_keys if (key.major, key.minor) in latest_per_major_minor and latest_per_major_minor[(key.major, key.minor)] == key] + ['All'],
            ),
        ]
        answers = inquirer.prompt(questions)
        if answers['release_tag'] == 'All':
            questions = [
                inquirer.List(
                    'release_tag',
                    message="Here are all tags. Which tag do you want to release?",
                    choices=[tags_list[key].name for key in sorted_release_keys],
                    carousel=True
                ),
            ]
            answers = inquirer.prompt(questions)
        release_tag = answers['release_tag']

    release_key = tag_to_key(release_tag)
    if release_key not in tags_list:
        raise DMakeException("Could not find target tag: {tag}.".format(tag=release_tag))
    else:
        prerelease = release_key.prerelease is not None
        release_tag = tags_list[release_key]
        target_commit = release_tag.commit
        tags_index = sorted_release_keys.index(release_key)

    # Look for previous version
    if tags_index == len(sorted_release_keys) - 1:
        change_log = "Initial commit"
    else:
        prev_key = sorted_release_keys[tags_index + 1]
        prev_version = tags_list[prev_key]
        no_prefix_next = remove_tag_prefix(release_tag.name)
        no_prefix_prev = remove_tag_prefix(prev_version.name)
        if semver.bump_major(no_prefix_prev) != no_prefix_next and \
           semver.bump_minor(no_prefix_prev) != no_prefix_next and \
           semver.bump_patch(no_prefix_prev) != no_prefix_next and \
           semver.bump_prerelease(no_prefix_prev) != no_prefix_next and \
            (release_key.major != prev_key.major or
             release_key.minor != prev_key.minor or
             release_key.patch != prev_key.patch or
             release_key.prerelease != prev_key.prerelease):
            raise DMakeException("Could not find any corresponding correct candidate previous version when bumping to {tag}. Previous version candidate: {prev}".format(tag=release_tag.name, prev=prev_version.name))

        # Compute change log
        # TODO: use https://github.com/vaab/gitchangelog
        common.run_shell_command2("git fetch --tags --quiet")
        change_log_cmd = "git log {prev}...{target} --pretty=%s".format(prev=prev_version.commit.sha, target=target_commit.sha)
        change_log = common.run_shell_command2(change_log_cmd)

        if change_log == "":
            print("No changes found. Exiting...")
            return

    # Creates the release
    repo.create_git_release(release_tag.name, release_tag.name, change_log, prerelease=prerelease, target_commitish=target_commit)
    print("Done ! Check it at: https://github.com/{owner}/{repo}/releases/tag/{tag}".format(owner=owner.name, repo=repo.name, tag=release_tag.name))
