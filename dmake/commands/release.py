import os

import dmake.common as common
import semver
from dmake.common import DMakeException


def remove_tag_prefix(tag):
    """Returns the tag name without the leading 'v'"""
    return tag[1:] if tag.startswith('v') else tag


def tag_to_version(tag):
    """
    Returns a VersionInfo of the provided tag or None if the version is invalid

    Args:
        tag (str): the string to convert into version
    """
    try:
        return semver.parse_version_info(remove_tag_prefix(tag))
    except ValueError:
        return None


def is_valid_bump(prev_version, next_version):
    """Returns True if the bump is valid according to Semantic Versionning

    A bump is valid if:
    -   The release version is strictly higher than the current version, including extensions
    -   No version is skipped when bumping the major/minor/patch part or
        finalizing (=removing extensions, i.e. prerelease and build parts).

    Note that a bump is invalid if only the build part differs. This behaviour may
    be too restrictive and change later.

    More info: https://semver.org or see examples in test/test_release_command.py

    Args:
        prev_version (VersionInfo): the current version
        next_version (VersionInfo): the version to release
    """
    if prev_version >= next_version:
        return False

    # Ensure no version is skipped
    # Prereleases and builds are not taken in account as their token can change
    # Example: (1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-beta)
    if prev_version.prerelease is None and next_version.prerelease is None and \
            prev_version.build is None and next_version.build is None:
        return semver.bump_major(str(prev_version)) == str(next_version) or \
               semver.bump_minor(str(prev_version)) == str(next_version) or \
               semver.bump_patch(str(prev_version)) == str(next_version)

    # Ensure no version is skipped if finalizing the version
    elif prev_version.prerelease is not None and next_version.prerelease is None:
        return tag_to_version(semver.finalize_version(str(prev_version))) == next_version
    else:
        return True


def entry_point(options):
    # lazy import for faster cli
    from github import Github
    import inquirer

    app = getattr(options, 'app')
    release_tag = getattr(options, 'tag')

    token = os.getenv('DMAKE_GITHUB_TOKEN', None)
    owner = os.getenv('DMAKE_GITHUB_OWNER', None)
    if not token:
        raise DMakeException(
            "Your need to define your Github Access Token by setting the DMAKE_GITHUB_TOKEN environment variable")
    if not owner:
        raise DMakeException(
            "Your need to define your Github account/organization name by setting the DMAKE_GITHUB_OWNER environment variable")

    # Access Github repo
    g = Github(token)
    owner = g.get_user(owner)
    repo = owner.get_repo(app)

    # List releases
    github_tag_list = {}
    for tag in repo.get_tags():
        version = tag_to_version(tag.name)
        if version is not None:
            github_tag_list[version] = tag
    sorted_release_versions = sorted(github_tag_list.keys(), reverse=True)
    latest_per_major_minor = {}
    for version in sorted_release_versions:
        if (version.major, version.minor) not in latest_per_major_minor:
            latest_per_major_minor[(version.major, version.minor)] = version

    # Ask for previous version
    if release_tag is None:
        choices = []
        for key in sorted_release_versions:
            if (key.major, key.minor) in latest_per_major_minor and latest_per_major_minor[(key.major, key.minor)] == key:
                choices.append(github_tag_list[key].name)
        choices.append('Other')
        questions = [
            inquirer.List(
                'release_tag',
                message="Here are only the latest tags per major-minor version. Which tag do you want to release on?",
                choices=choices,
            ),
        ]
        answers = inquirer.prompt(questions)
        if answers['release_tag'] == 'Other':
            questions = [
                inquirer.List(
                    'release_tag',
                    message="Here are all the tags. Which tag do you want to release on?",
                    choices=[github_tag_list[key].name for key in sorted_release_versions],
                    carousel=True
                ),
            ]
            answers = inquirer.prompt(questions)
        release_tag = answers['release_tag']

    release_version = tag_to_version(release_tag)
    if release_version not in github_tag_list:
        raise DMakeException("Could not find target tag: {tag}.".format(tag=release_tag))
    else:
        prerelease = release_version.prerelease is not None
        release_tag = github_tag_list[release_version]
        target_commit = release_tag.commit
        tags_index = sorted_release_versions.index(release_version)

    # Look for previous version
    if tags_index == len(sorted_release_versions) - 1:
        change_log = "Initial release"
    else:
        prev_version = sorted_release_versions[tags_index + 1]
        prev_github_tag = github_tag_list[prev_version]
        next_version = tag_to_version(release_tag.name)

        if not is_valid_bump(prev_version, next_version):
            raise DMakeException(
                "Could not find any corresponding correct candidate previous version when bumping to {tag}. Previous version candidate: {prev}".format(
                    tag=release_tag.name, prev=prev_github_tag.name))

        # Compute change log
        # TODO: use https://github.com/vaab/gitchangelog
        common.run_shell_command2("git fetch --tags --quiet")
        change_log_cmd = "git log {prev}...{target} --pretty=%s".format(prev=prev_github_tag.commit.sha,
                                                                        target=target_commit.sha)
        change_log = common.run_shell_command2(change_log_cmd)

        if change_log == "":
            print("No changes found. Exiting...")
            return

        # Add dashes to make a markdown list
        change_log = '\n'.join(['- ' + line for line in change_log.split('\n')])

    # Creates the release
    repo.create_git_release(release_tag.name, release_tag.name, change_log, prerelease=prerelease,
                            target_commitish=target_commit)
    print("Done ! Check it at: https://github.com/{owner}/{repo}/releases/tag/{tag}".format(owner=owner.name,
                                                                                            repo=repo.name,
                                                                                            tag=release_tag.name))
