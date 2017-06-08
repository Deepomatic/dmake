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

class NotGitRepositoryException(DMakeException):
    def __init__(self):
        super(NotGitRepositoryException, self).__init__('Not a GIT repository')

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

escape_re = re.compile(r'(\$|\\|\"|\')')
def escape_cmd(cmd):
    return escape_re.sub(lambda m:{'$':'\$','\\':'\\\\','"':'\\"','\'':'\\\''}[m.group()], cmd)

def wrap_cmd(cmd):
    return '"%s"' % cmd.replace('"', '\\"')

def eval_str_in_env(cmd):
    cmd = 'echo %s' % wrap_cmd(cmd)
    return run_shell_command(cmd).strip()

# Docker has some trouble mounting volumes with trailing '/'.
# See http://stackoverflow.com/questions/38338612/mounting-file-system-in-docker-fails-sometimes
def join_without_slash(*args):
    path = os.path.join(*args)
    if len(path) > 0 and path[-1] == '/':
        path = path[:-1]
    return path

###############################################################################

def find_repo_root(root_dir):
    sub_dir = ''
    while True:
        if os.path.isdir(os.path.join(root_dir, '.git')):
            break
        else:
            if root_dir == '/':
                raise NotGitRepositoryException()
            sub_dir = os.path.join(os.path.basename(root_dir), sub_dir)
            root_dir = os.path.normpath(os.path.join(root_dir, '..'))
            if root_dir.startswith('..'):
                return None, None
    sub_dir = os.path.normpath(sub_dir)
    if sub_dir == '.':
        sub_dir = '' # IMPORTANT: Need to get rid of the leading '.' to unify behaviour
    return root_dir, sub_dir

###############################################################################

pulled_config_dirs = {}
def pull_config_dir(root_dir):
    global pulled_config_dirs

    if not os.path.isdir(root_dir):
        raise DMakeException('Could not find directory: %s' % root_dir)

    root_dir, _ = find_repo_root(root_dir)
    if root_dir is None:
        return

    if root_dir in pulled_config_dirs:
        return

    logger.info("Pulling config from: %s" % root_dir)
    os.system("cd %s && git pull origin master" % root_dir)
    pulled_config_dirs[root_dir] = True

###############################################################################

if sys.version_info >= (3,0):
    from deepomatic.dmake.python_3x import is_string, read_input
else:
    from deepomatic.dmake.python_2x import is_string, read_input

###############################################################################

def init(_command, _root_dir, _app, _options):
    global root_dir, tmp_dir, config_dir, cache_dir, key_file
    global branch, target, is_pr, pr_id, build_id, commit_id, force_full_deploy
    global repo_url, repo, use_pipeline, is_local, skip_tests
    global build_description
    global command, options, uname
    root_dir = os.path.join(_root_dir, '')
    command = _command
    options = _options

    config_dir = os.getenv('DMAKE_CONFIG_DIR', None)
    if config_dir is None:
        raise DMakeException("DMake seems to be badly configured: environment variable DMAKE_CONFIG_DIR is missing. Try to run %s again." % os.path.join(os.getenv('DMAKE_PATH', ""), 'install.sh'))
    cache_dir = os.path.join(root_dir, '.dmake')
    try:
        os.mkdir(cache_dir)
    except OSError:
        pass

    tmp_dir = run_shell_command("dmake_make_tmp_dir")
    os.environ['DMAKE_TMP_DIR'] = tmp_dir

    # Get uname
    uname = run_shell_command("uname")

    # Make sure DMAKE_ON_BUILD_SERVER is correctly configured
    is_local = os.getenv('DMAKE_ON_BUILD_SERVER', 0) != "1"

    # Set skip test variable
    skip_tests = os.getenv('DMAKE_SKIP_TESTS', "false") == "true"

    use_pipeline = True
    branch   = os.getenv('BRANCH_NAME', None)
    if branch is None:
        use_pipeline = False
        target = os.getenv('ghprbTargetBranch', None)
        pr_id  = os.getenv('ghprbPullId', None)
        build_id = os.getenv('BUILD_NUMBER', '0')
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
        build_id = os.getenv('BUILD_ID', '0')
    is_pr = target is not None
    force_full_deploy = False

    if 'branch' in options and options.branch:
        branch = options.branch

    # Modify command if (is_pr && !is_local)
    if is_pr and not is_local:
        assert(command == "deploy")
        command = "test"

    # Find repo
    repo_url = run_shell_command('git config --get remote.origin.url')
    repo = re.search('/([^/]*)\.git', repo_url).groups()[0]
    repo_github_owner = re.search('github.com[:/](.*?)/', repo_url)
    commit_id = run_shell_command('git rev-parse HEAD')

    if repo_github_owner is not None:
        repo_github_owner = repo_github_owner.groups()[0]

    # Set Job description
    if _app == "" or _app == "*":
        _app = "All targets"
    build_description = None
    if use_pipeline:
        run_shell_command('git submodule update --init', ignore_error = True)
        if is_pr:
            build_description = "<a href=%s>PR #%s</a>: %s" % (
                os.getenv('CHANGE_URL'),
                os.getenv('CHANGE_ID'),
                os.getenv('CHANGE_TITLE'))
        else:
            if repo_github_owner is not None:
                build_description = "Branch <a href=%s>%s</a> - %s" % (
                    "https://github.com/%s/%s/tree/%s" % (repo_github_owner, repo, branch),
                    branch, _app)

    os.environ["REPO"]        = repo
    os.environ["BRANCH"]      = str(branch)
    os.environ["COMMIT_ID"]   = commit_id
    os.environ["BUILD"]       = str(build_id)

    logger.info("===============")
    logger.info("REPO : %s" % repo)
    if build_id != 0:
        logger.info("BUILD : %s" % build_id)
    if is_pr:
        logger.info("PR : %s -> %s" % (branch, target))
    else:
        logger.info("BRANCH : %s" % branch)
    logger.info("COMMIT_ID : %s" % commit_id[:7])
    logger.info("===============")

    # Check the SSH Key for cloning private repositories is correctly set up
    key_file = os.getenv('DMAKE_SSH_KEY', None)
    if key_file == '':
        key_file = None
    if key_file is not None:
        if os.path.isfile(key_file):
            if os.getenv('SSH_AUTH_SOCK', None) is None:
                lines = run_shell_command("eval `ssh-agent -s` && echo $SSH_AUTH_SOCK && echo $SSH_AGENT_PID").split('\n')
                os.environ['SSH_AUTH_SOCK'] = lines[-2]
                run_shell_command('echo %s >> %s/processes_to_kill.txt' % (lines[-1], tmp_dir))
            logger.info("Adding SSH key %s to SSH Agent" % key_file)
            run_shell_command("ssh-add %s" % key_file, ignore_error = True)
        else:
            logger.warning("WARNING: DMAKE_SSH_KEY does not point to a valid file. You won't be able to clone private repositories.")
            key_file = None
