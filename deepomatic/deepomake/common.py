import os
import sys
import logging
import subprocess
import re

# Set logger
logger = logging.getLogger("deepomatic.dmake")
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())

###############################################################################

class ShellError(Exception):
    def __init__(self, msg):
        super(ShellError, self).__init__(msg)

class DMakeException(Exception):
    def __init__(self, msg):
        super(DMakeException, self).__init__(msg)

###############################################################################

def run_shell_command(cmd, ignore_error = False):
    command = ['bash', '-c', cmd]
    p = subprocess.Popen(command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    stdout, stderr = p.communicate()
    if len(stderr) > 0 and not ignore_error:
        raise ShellError(stderr.decode())
    return stdout.strip().decode()

def array_to_env_vars(array):
    return '#@#'.join([a.replace("@", "\\@") for a in array])

def eval_str_in_env(cmd):
    return run_shell_command('echo "%s"' % cmd.replace('"', '\\"')).strip()

# Docker has some trouble mounting volumes with trailing '/'.
# See http://stackoverflow.com/questions/38338612/mounting-file-system-in-docker-fails-sometimes
def join_without_slash(*args):
    path = os.path.join(*args)
    if len(path) > 0 and path[-1] == '/':
        path = path[:-1]
    return path

###############################################################################

if sys.version_info >= (3,0):
    from deepomatic.deepomake.python_3x import is_string
else:
    from deepomatic.deepomake.python_2x import is_string

###############################################################################

def init(_command, _root_dir, _options):
    global root_dir, tmp_dir, cache_dir, key_file
    global branch, target, is_pr, pr_id, build_id, commit_id
    global repo_url, repo, env_type, use_pipeline, is_local
    global build_description
    global command, options
    root_dir = os.path.join(_root_dir, '')
    command = _command
    options = _options

    cache_dir = os.path.join(root_dir, '.dmake')
    try:
        os.mkdir(cache_dir)
    except OSError:
        pass

    tmp_dir = run_shell_command("deepomake_make_tmp_dir")
    os.environ['DMAKE_TMP_DIR'] = tmp_dir

    # Make sure DMAKE_ON_BUILD_SERVER is correctly configured
    is_local = os.getenv('DMAKE_ON_BUILD_SERVER', 0) != "1"
    if is_local:
        assert(os.getenv('USER') != "jenkins")
    else:
        run_shell_command('sudo chown jenkins * -R')

    use_pipeline = True
    branch   = os.getenv('BRANCH_NAME', None)
    if branch is None:
        use_pipeline = False
        target = os.getenv('ghprbTargetBranch', None)
        pr_id  = os.getenv('ghprbPullId', None)
        build_id = os.getenv('BUILD_NUMBER')
        if target is None:
            branch = os.getenv('GIT_BRANCH')
        else:
            branch = "PR-%s" % pr_id
        if branch is None:
            branch = run_shell_command("git rev-parse --abbrev-ref HEAD")
        if branch is not None:
            branch = branch.split('/')
            if len(branch) > 1:
                branch = '/'.join(branch[1:])
            else:
                branch = branch[0]
    else:
        target   = os.getenv('CHANGE_TARGET', None)
        pr_id    = os.getenv('CHANGE_ID')
        build_id = os.getenv('BUILD_ID')
    is_pr = target is not None
    if build_id is None:
        build_id = "0"

    branch = branch.replace('#', 'X')

    # Find repo
    repo_url = run_shell_command('git config --get remote.origin.url')
    repo = re.search('/([^/]*)\.git', repo_url).groups()[0]
    repo_github_owner = re.search('github.com[:/](.*?)/', repo_url)
    commit_id = run_shell_command('git rev-parse HEAD')

    if repo_github_owner is not None:
        repo_github_owner = repo_github_owner.groups()[0]

    # Set env_type
    if branch == "master":
        env_type = "prod"
    elif branch == "stag":
        env_type = "stag"
    else:
        env_type = "dev"

    # Set Job description
    build_description = None
    if use_pipeline:
        run_shell_command('git submodule update --init')
        if is_pr:
            build_description = "<a href=%s>PR #%s</a>: %s" % (
                os.getenv('CHANGE_URL'),
                os.getenv('CHANGE_ID'),
                os.getenv('CHANGE_TITLE'))
        else:
            if repo_github_owner is not None:
                build_description = "Branch <a href=%s>%s</a>" % (
                    "https://github.com/%s/%s/tree/%s" % (repo_github_owner, repo, branch),
                    branch)

    # Load configuration from env repository
    pull_config_dir = True
    config_dir = os.getenv('CONFIG_DIR')
    if config_dir is None:
        config_dir = os.getenv('DEEPOMATIC_CONFIG_DIR')
        pull_config_dir = False
    if config_dir is None:
        logger.warning("[DEEPOMATIC_]CONFIG_DIR not defined, not sourcing environment variables")
    else:
        if pull_config_dir:
            logger.info("Pulling config from: %s" % config_dir)
            os.system("cd %s && git pull origin master" % config_dir)

        # Source environment variables
        output = run_shell_command('source %s/%s.sh && env' % (config_dir, env_type))
        output = output.split('\n')
        for line in output:
            line = line.strip()
            if len(line) == 0:
                continue
            (key, _, value) = line.partition("=")
            os.environ[key] = value

    os.environ["REPO"]        = repo
    os.environ["BUILD"]       = build_id
    os.environ["BRANCH"]      = str(branch)
    os.environ["COMMIT_ID"]   = commit_id
    os.environ["ENV_TYPE"]    = env_type

    logger.info("===============")
    logger.info("REPO : %s" % repo)
    if build_id != "0":
        logger.info("BUILD : %s" % build_id)
    if is_pr:
        logger.info("PR : %s -> %s" % (branch, target))
    else:
        logger.info("BRANCH : %s" % branch)
    logger.info("COMMIT_ID : %s" % commit_id[:7])
    logger.info("ENV_TYPE : %s" % env_type)
    logger.info("===============")

    # Check the SSH Key for cloning private repositories is correctly set up
    key_file = os.getenv('DMAKE_SSH_KEY', None)
    if key_file == '':
        key_file = None
    if key_file is not None:
        if os.path.isfile(key_file):
            if os.getenv('SSH_AUTH_SOCK', None) is not None:
                if run_shell_command("ssh-add -L").find(key_file) < 0:
                    logger.info("Adding SSH key %s to SSH Agent" % key_file)
                    run_shell_command("ssh-add %s" % key_file, ignore_error = True)
        else:
            raise DMakeException('DMAKE_SSH_KEY does not point to a valid file.')
