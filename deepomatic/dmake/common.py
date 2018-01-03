import os
import sys
import logging
import subprocess
import re
from ruamel.yaml import YAML

# Set logger
logger = logging.getLogger("deepomatic.dmake")
logger.setLevel(logging.INFO) #TODO configurable
logger.addHandler(logging.StreamHandler())

###############################################################################

if sys.version_info >= (3,0):
    from deepomatic.dmake.python_3x import StringIO, is_string, to_string, read_input, subprocess_output_to_string
else:
    from deepomatic.dmake.python_2x import StringIO, is_string, to_string, read_input, subprocess_output_to_string

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

def yaml_ordered_load(stream):
    try:
        yaml = YAML(pure=True)
        data = yaml.load(stream)
        return data
    except Exception as e:
        raise DMakeException(str(e))

def yaml_ordered_dump(data, stream=None, default_flow_style=False):
    yaml=YAML()
    yaml.default_flow_style = default_flow_style
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    string_value = StringIO()
    yaml.dump(data, string_value)
    string_value = string_value.getvalue()
    if stream:
        stream.write(string_value)
    else:
        return string_value

###############################################################################

def run_shell_command(commands, ignore_error=False, additional_env=None, stdin=None, raise_on_return_code=False):
    if not isinstance(commands, list):
        commands = [commands]
    if additional_env is None:
        additional_env = {}

    env = os.environ.copy()
    env.update(additional_env)

    # don't trace shell execution when run from dmake process: it would be detected as an error otherwise
    env.pop('DMAKE_DEBUG', None)

    prev_stdout = subprocess.PIPE if stdin else None
    for cmd in commands:
        cmd = ['bash', '-c', cmd]
        p = subprocess.Popen(cmd, stdin = prev_stdout, stdout = subprocess.PIPE, stderr = subprocess.PIPE, env = env)
        prev_stdout = p.stdout
    stdout, stderr = p.communicate(stdin)
    if len(stderr) > 0 and not ignore_error and not raise_on_return_code:
        raise ShellError(subprocess_output_to_string(stderr))
    if raise_on_return_code and p.returncode != 0:
        raise ShellError("return code: %s; stdout: %sstderr: %s" % (p.returncode, subprocess_output_to_string(stdout), subprocess_output_to_string(stderr)))
    return subprocess_output_to_string(stdout).strip()

def array_to_env_vars(array):
    return '#@#'.join([a.replace("@", "\\@") for a in array])

escape_re = re.compile(r'(\$|\\|\"|\')')
def escape_cmd(cmd):
    return escape_re.sub(lambda m:{'$':'\$','\\':'\\\\','"':'\\"','\'':'\\\''}[m.group()], cmd)

def wrap_cmd(cmd):
    return '"%s"' % cmd.replace('"', '\\"')

def eval_str_in_env(cmd, env=None):
    if env is None:
        env = {}
    cmd = 'echo %s' % wrap_cmd(cmd)
    return run_shell_command(cmd, additional_env=env).strip()

# Docker has some trouble mounting volumes with trailing '/'.
# See http://stackoverflow.com/questions/38338612/mounting-file-system-in-docker-fails-sometimes
def join_without_slash(*args):
    path = os.path.join(*args)
    if len(path) > 0 and path[-1] == '/':
        path = path[:-1]
    return path

###############################################################################

def find_repo_root(path=os.getcwd()):
    root_dir = run_shell_command('git -C %s rev-parse --show-toplevel' %(path))
    sub_dir = os.path.relpath(path, root_dir)
    if sub_dir == '.':
        sub_dir = '' # IMPORTANT: Need to get rid of the leading '.' to unify behaviour
    return root_dir, sub_dir

###############################################################################

pulled_config_dirs = {}
def pull_config_dir(root_dir):
    global pulled_config_dirs
    global do_pull_config_dir

    if not do_pull_config_dir:
        return

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

def get_dmake_build_type():
    global is_release_branch
    assert(is_release_branch is not None)
    return "release" if is_release_branch else "testing"

###############################################################################

def init(_command, _root_dir, _app, _options):
    global root_dir, tmp_dir, config_dir, cache_dir, relative_cache_dir, key_file
    global branch, target, is_pr, pr_id, build_id, commit_id, force_full_deploy
    global repo_url, repo, use_pipeline, is_local, skip_tests, is_release_branch
    global build_description
    global command, options, uname
    global do_pull_config_dir
    root_dir = os.path.join(_root_dir, '')
    command = _command
    options = _options

    config_dir = os.getenv('DMAKE_CONFIG_DIR', None)
    if config_dir is None:
        raise DMakeException("DMake seems to be badly configured: environment variable DMAKE_CONFIG_DIR is missing. Try to run %s again." % os.path.join(os.getenv('DMAKE_PATH', ""), 'install.sh'))
    relative_cache_dir = '.dmake'
    cache_dir = os.path.join(root_dir, relative_cache_dir)
    try:
        os.mkdir(cache_dir)
    except OSError:
        pass
    do_pull_config_dir = os.getenv('DMAKE_PULL_CONFIG_DIR', '1') != '0'

    tmp_dir = run_shell_command("dmake_make_tmp_dir")
    os.environ['DMAKE_TMP_DIR'] = tmp_dir

    # Get uname
    uname = run_shell_command("uname")

    # Make sure DMAKE_ON_BUILD_SERVER is correctly configured
    is_local = os.getenv('DMAKE_ON_BUILD_SERVER', 0) != "1"

    # Set skip test variable
    skip_tests = os.getenv('DMAKE_SKIP_TESTS', "false") == "true"

    # Currently set if any dmake file describes a deploy stage matching current branch; updated after files parsing
    is_release_branch = None

    use_pipeline = True
    # For PRs on Jenkins this will give the source branch name
    branch = os.getenv('CHANGE_BRANCH', None)
    # When not PR, this will be the actual branch name
    if branch is None:
        branch = os.getenv('BRANCH_NAME', None)
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
    repo = re.search('/([^/]*?)(\.git)?$', repo_url).group(1)
    assert repo
    repo_github_owner = re.search('github.com[:/](.*?)/', repo_url)
    assert repo_github_owner
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
            build_description = "%s/%s: <a href=%s>PR #%s</a>: %s" % (
                repo_github_owner or '', repo,
                os.getenv('CHANGE_URL'),
                os.getenv('CHANGE_ID'),
                os.getenv('CHANGE_TITLE'))
        else:
            if repo_github_owner is not None:
                build_description = "%s/%s: <a href=%s>%s</a> - %s" % (
                    repo_github_owner, repo,
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
