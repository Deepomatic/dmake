import os
import sys
import argparse
from datetime import datetime
import hashlib
import io
import logging
import subprocess
import re
from ruamel.yaml import YAML
from ruamel.yaml.emitter import Emitter as YAML_Emitter
import uuid

# Set logger
logger = logging.getLogger("dmake")
logger.setLevel(logging.INFO) #TODO configurable
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

class SharedVolumeNotFoundException(DMakeException):
    def __init__(self, name):
        super(SharedVolumeNotFoundException, self).__init__("Unknown volume named '%s'" % (name))
        self.name = name

class DockerConfigFileNotFoundException(DMakeException):
    def __init__(self, filename):
        super(DockerConfigFileNotFoundException, self).__init__('Docker config file not found (needed for registry credentials: maybe run `docker login`): %s' % (filename))

###############################################################################

class DependenciesBooleanAction(argparse.Action):
    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        super(DependenciesBooleanAction, self).__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if option_string in ["--no-dependencies", "-s", "--standalone"]:
            value = False
        elif option_string in ["-d", "--dependencies"]:
            value = True
        else:
            assert False, "Invalid DependenciesBooleanAction option: {}".format(option_string)
        setattr(namespace, self.dest, value)

class FlagBooleanAction(argparse.Action):
    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        super(FlagBooleanAction, self).__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if option_string.startswith("--no-"):
            value = False
        else:
            value = True
        setattr(namespace, self.dest, value)

###############################################################################

class YAMLEmitterNoVersionDirective(YAML_Emitter):
    def write_version_directive(self, version_text):
        # disable emitting version directive (%YAML 1.1)
        pass

def yaml_ordered_load(stream, all=False):
    try:
        yaml = YAML(typ='safe', pure=True)
        # kubectl and everyone else uses yaml 1.1
        yaml.version = (1, 1)
        data = list(yaml.load_all(stream)) if all else yaml.load(stream)
        return data
    except Exception as e:
        raise DMakeException(str(e))

def yaml_ordered_dump(data, stream=None, default_flow_style=False, all=False, normalize_indent=False):
    return_string = False
    if stream is None:
        stream = io.StringIO()
        return_string = True
    yaml = YAML(pure=True)
    # simplify concatenating yaml files
    yaml.explicit_start = True
    # kubernetes reads yaml 1.1, notably interprets `no` as boolean instead of string vs default ruamel which dumps yaml 1.2
    yaml.version = (1, 1)
    # kubectl does not tolerate %YAML 1.1 directive, disabling it
    yaml.Emitter = YAMLEmitterNoVersionDirective
    if normalize_indent:
        yaml.default_flow_style = default_flow_style
        yaml.width = 4096
        yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.dump_all(data, stream) if all else yaml.dump(data, stream)
    if return_string:
        return stream.getvalue()

###############################################################################

def append_command(commands, cmd, prepend = False, **args):
    def check_cmd(args, required, optional = []):
        for a in required:
            if a not in args:
                raise DMakeException("%s is required for command %s" % (a, cmd))
        for a in args:
            if a not in required and a not in optional:
                raise DMakeException("Unexpected argument %s for command %s" % (a, cmd))
    if cmd == "stage":
        check_cmd(args, ['name', 'concurrency'])
    elif cmd == "stage_end":
        check_cmd(args, [])
    elif cmd == "lock":
        check_cmd(args, ['label'])
    elif cmd == "lock_end":
        check_cmd(args, [])
    elif cmd == "timeout":
        check_cmd(args, ['time'])
    elif cmd == "timeout_end":
        check_cmd(args, [])
    elif cmd == "echo":
        check_cmd(args, ['message'])
    elif cmd == "sh":
        check_cmd(args, ['shell'])
    elif cmd == "read_sh":
        check_cmd(args, ['var', 'shell'], optional = ['fail_if_empty'])
        if 'fail_if_empty' not in args:
            args['fail_if_empty'] = False
    elif cmd == "env":
        check_cmd(args, ['var', 'value'])
    elif cmd == "git_tag":
        check_cmd(args, ['tag'])
    elif cmd == "junit":
        check_cmd(args, ['report', 'service_name', 'mount_point'])
    elif cmd == "cobertura":
        check_cmd(args, ['report', 'service_name', 'mount_point'])
    elif cmd == "publishHTML":
        check_cmd(args, ['directory', 'index', 'title', 'service_name', 'mount_point'])
    else:
        raise DMakeException("Unknown command %s" % cmd)
    cmd = (cmd, args)
    if prepend:
        commands.insert(0, cmd)
    else:
        commands.append(cmd)

###############################################################################

def run_shell_command(commands, ignore_error=False, additional_env=None, stdin=None, raise_on_return_code=False):
    """Deprecated, use run_shell_command2 instead."""
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
        p = subprocess.Popen(cmd, stdin=prev_stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        prev_stdout = p.stdout

    # python3 compatibility
    if sys.version_info >= (3, 0) and stdin is not None:
        stdin = stdin.encode('utf-8')

    stdout, stderr = p.communicate(stdin)

    if len(stderr) > 0 and not ignore_error and not raise_on_return_code:
        raise ShellError(stderr.decode())
    if raise_on_return_code and p.returncode != 0:
        raise ShellError("return code: %s; stdout: %sstderr: %s" % (p.returncode, stdout.decode(), stderr.decode()))
    return stdout.decode().strip()

def run_shell_command2(commands, additional_env=None, stdin=None):
    return run_shell_command(commands, ignore_error=False, additional_env=additional_env, stdin=stdin, raise_on_return_code=True)

def make_tmp_dir(name, in_root_dir=False):
    additional_env = {}
    if in_root_dir:
        # force generate directly in /tmp
        additional_env['DMAKE_TMP_DIR'] = ""
    return run_shell_command2('dmake_make_tmp_dir "{name}"'.format(name=name),
                              additional_env=additional_env)

def array_to_env_vars(array):
    return '#@#'.join([a.replace("@", "\\@") for a in array])

escape_re = re.compile(r'(\$|\\|\"|\')')
def escape_cmd(cmd):
    return escape_re.sub(lambda m:{'$':'\$','\\':'\\\\','"':'\\"','\'':'\\\''}[m.group()], cmd)

def wrap_cmd(cmd):
    return '"%s"' % cmd.replace('"', '\\"')

def wrap_cmd_simple_quotes(cmd):
    # Example: foo'bar -> 'foo'\''bar' (i.e. 3 concatenated literal strings: 'foo', \' and 'bar', which is interpreted by bash as one arg: foo'bar)
    return "'%s'" % cmd.replace("'", "'\\''")

def eval_str_in_env(value, env=None, strict=False, source=None):
    if env is None:
        env = {}
    cmd = ''
    if strict:
        cmd += 'set -euo pipefail; '
    if source:
        cmd += 'source %s && ' % (source)
    cmd += 'echo %s' % wrap_cmd(value)
    return run_shell_command(cmd, additional_env=env).strip()

def eval_values_in_env(d, env=None, strict=False, source=None):
    for key in d:
        d[key] = eval_str_in_env(d[key], env, strict, source)

# Docker has some trouble mounting volumes with trailing '/'.
# See http://stackoverflow.com/questions/38338612/mounting-file-system-in-docker-fails-sometimes
def join_without_slash(*args):
    path = os.path.join(*args)
    if len(path) > 0 and path[-1] == '/':
        path = path[:-1]
    return path

def sanitize_name(name, mode='kubernetes'):
    """
    Return sanitized name that follow a regex specified by mode:
    - '[a-z0-9]([-a-z0-9]*[a-z0-9])?' (kubernetes name restrictions)
    - '[a-zA-Z0-9][a-zA-Z0-9_.-]+' (docker name restrictions)
    """
    if mode == 'kubernetes':
        name = name.lower()
        name = re.sub(r'[^a-z0-9\-]+', '-', name)
        name = name.lstrip('-')
    elif mode == 'docker':
        name = re.sub(r'[^a-zA-Z0-9_.\-]+', '-', name)
        name = name.lstrip('_.-')
    else:
        assert False, 'Invalid sanitize mode'
    return name

def sanitize_name_unique(name, mode):
    sanitized_name = sanitize_name(name, mode)
    if sanitized_name == name:
        return name
    unique = hashlib.sha256(name.encode('UTF-8')).hexdigest()[:10]
    return "{}-{}".format(sanitized_name, unique)


###############################################################################

def find_repo_root(path=os.getcwd()):
    root_dir = run_shell_command('git -C %s rev-parse --show-toplevel' % (path))
    sub_dir = os.path.relpath(path, root_dir)
    if sub_dir == '.':
        sub_dir = ''  # IMPORTANT: Need to get rid of the leading '.' to unify behaviour
    return root_dir, sub_dir

def git_get_upstream_branch_remote(branch):
    try:
        upstream_branch = run_shell_command('git rev-parse --abbrev-ref --symbolic-full-name {}@{{upstream}} --'.format(branch), raise_on_return_code=True)
    except ShellError:
        upstream_branch = None
    if not upstream_branch:
        # assume 'origin' as remote name
        return 'origin'
    if '/' not in upstream_branch:
        # upstream branch is local, get its own upstream
        return git_get_upstream_branch_remote(upstream_branch)
    remote = upstream_branch.split('/')[0]
    return remote

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

def dump_debug_dot_graph(dependencies, nodes_height):
    if not generate_dot_graph:
        return

    from graphviz import Digraph

    def node2node_id(node):
        # there is a bug in graphviz around `:` escaping, see https://github.com/xflr6/graphviz/issues/53
        return str(node).replace(':', '_')

    def node2label(node):
        label = '{}\n{}\n{}'.format(*node)
        if node in nodes_height:
            label += '\nheight={}'.format(nodes_height[node])
        return label

    dot = Digraph(comment='DMake Services', filename=dot_graph_filename, format=dot_graph_format)
    dot.attr('node', shape='box')

    # group nodes by commands
    commands = {}
    for node, deps in sorted(dependencies.items()):
        command = node[0]
        if command not in commands:
            commands[command] = []
        commands[command].append((node, deps))
    for command, nodes_deps in sorted(commands.items()):
        # sub graph with same rank: horizontal node alignment per command
        with dot.subgraph() as s:
            s.attr(rank='same')
            for node, deps in sorted(nodes_deps):
                # create nodes
                s.node(node2node_id(node), label=node2label(node))
                for dep in sorted(deps):
                    # create edges
                    dot.edge(node2node_id(node), node2node_id(dep))

    if dot_graph_filename is not None:
        dot.render()
        logger.info("Generated debug DOT graph: '%s' and '%s'" % (dot_graph_filename, dot_graph_filename + '.' + dot_graph_format))
    return dot

###############################################################################

def init(_options, early_exit=False):
    global generate_dot_graph, exit_after_generate_dot_graph, dot_graph_filename, dot_graph_format
    global root_dir, sub_dir, tmp_dir, config_dir, cache_dir, relative_cache_dir, key_file
    global branch, target, is_pr, pr_id, build_id, commit_id, name_prefix, image_tag_prefix, force_full_deploy
    global remote, repo_url, repo, use_pipeline, is_local, skip_tests, is_release_branch
    global no_gpu, need_gpu
    global build_description
    global command, options, uname
    global do_pull_config_dir
    global use_host_ports
    global session_id
    global session_timestamp
    global change_detection

    options = _options
    command = _options.cmd

    if command == 'build':
        command = 'build_docker'

    if command == 'completion':
        early_exit = True

    generate_dot_graph = options.debug_graph or options.debug_graph_and_exit
    exit_after_generate_dot_graph = options.debug_graph_and_exit
    dot_graph_filename = options.debug_graph_output_filename
    dot_graph_format = options.debug_graph_output_format

    change_detection = False  # set in core.make()

    try:
        root_dir, sub_dir = find_repo_root()
    except ShellError as e:
        raise DMakeException("Current directory is not a Git repository:\n{}".format(str(e)))

    root_dir = os.path.join(root_dir, '')  # make sure it is suffixed by /

    session_id = uuid.uuid4()
    session_timestamp = datetime.utcnow()

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
    use_host_ports = os.getenv('DMAKE_USE_HOST_PORTS', '0') != '0'

    # Get uname
    uname = run_shell_command("uname")

    # Make sure DMAKE_ON_BUILD_SERVER is correctly configured
    is_local = os.getenv('DMAKE_ON_BUILD_SERVER', 0) != "1"

    # Set skip test variable
    skip_tests = os.getenv('DMAKE_SKIP_TESTS', "false") in ["1", "true"]

    # Set no_gpu variable
    no_gpu = os.getenv('DMAKE_NO_GPU', "false") in ["1", "true"]
    need_gpu = False

    # Currently set if any dmake file describes a deploy stage matching current branch; updated after files parsing
    is_release_branch = None

    # For PRs on Jenkins this will give the source branch name
    branch = os.getenv('CHANGE_BRANCH', None)
    if branch is None:
        # When on Jenkins but not PR, this will be the actual branch name
        branch = os.getenv('BRANCH_NAME', None)
    if branch is None:
        # Not on Jenkins: bash mode: do not emit jenkins pipeline script
        branch = run_shell_command("git rev-parse --abbrev-ref HEAD")
        use_pipeline = False
        target = os.getenv('CHANGE_TARGET', '@{upstream}')
        pr_id  = None
        build_id = os.getenv('BUILD_NUMBER', '0')
        is_pr = False
    else:
        # On Jenkins, assume multibranch project
        use_pipeline = True
        target   = os.getenv('CHANGE_TARGET', None)
        pr_id    = os.getenv('CHANGE_ID')
        build_id = os.getenv('BUILD_ID', '0')
        is_pr = target is not None
    force_full_deploy = False

    if 'branch' in options and options.branch:
        branch = options.branch

    # Modify command if (is_pr && !is_local)
    # TODO remove later: has beend moved to Jenkinsfile instead
    if is_pr and not is_local and command == "deploy":
        command = "test"

    # Find git info
    repo = ''
    repo_url = None
    repo_github_owner = None
    commit_id = ''
    # Find remote
    upstream_branch = run_shell_command('git rev-parse --abbrev-ref --symbolic-full-name @{upstream}', ignore_error=True)
    if not upstream_branch:
        # assume 'origin' as remote name
        remote = 'origin'
    else:
        remote = upstream_branch.split('/')[0]
    # Find repo
    remote = git_get_upstream_branch_remote('HEAD')
    repo_url = run_shell_command('git config --get remote.%s.url' % (remote), ignore_error=True)
    repo = re.search('/([^/]*?)(\.git)?$', repo_url)
    if repo is not None:
        repo = repo.group(1)
    else:
        # use local directory name for local repos with no remote
        repo_root, _ = find_repo_root()
        repo = os.path.basename(repo_root)
    assert repo, "repo cannot be empty"
    repo_github_owner = re.search('github.com[:/](.*?)/', repo_url)
    if repo_github_owner is not None:
        repo_github_owner = repo_github_owner.groups()[0]
    commit_id = run_shell_command('git rev-parse HEAD')

    # Generate name prefix: readable, unique, stable identifier
    name_prefix = sanitize_name_unique('{repo}.{branch}.{build_id}'.format(repo=repo, branch=branch, build_id=build_id), mode='docker')

    tmp_dir = make_tmp_dir(name_prefix, in_root_dir=True)
    os.environ['DMAKE_TMP_DIR'] = tmp_dir

    # Generate default image tag prefix
    image_tag_prefix = sanitize_name_unique(branch, mode='docker')

    # Set Job description
    build_description = None
    if use_pipeline:
        run_shell_command('git submodule update --init', ignore_error=True)
        if is_pr:
            build_description = "%s/%s: <a href=%s>PR #%s</a>: %s" % (
                repo_github_owner or '', repo,
                os.getenv('CHANGE_URL'),
                os.getenv('CHANGE_ID'),
                os.getenv('CHANGE_TITLE'))
        else:
            if repo_github_owner is not None:
                app = getattr(options, 'service')
                build_description = "%s/%s: <a href=%s>%s</a> - %s" % (
                    repo_github_owner, repo,
                    "https://github.com/%s/%s/tree/%s" % (repo_github_owner, repo, branch),
                    branch, "All targets" if app == '*' else app)

    os.environ["REPO"]        = repo
    os.environ["BRANCH"]      = str(branch)
    os.environ["COMMIT_ID"]   = commit_id
    os.environ["BUILD"]       = str(build_id)
    os.environ["REPO_SANITIZED"]   = sanitize_name(repo)
    os.environ["BRANCH_SANITIZED"] = sanitize_name(str(branch))
    os.environ["IMAGE_TAG_PREFIX"] = image_tag_prefix

    if early_exit:
        return

    logger.info("===============")
    logger.info("REPO : %s" % repo)
    if build_id != 0:
        logger.info("BUILD : %s" % build_id)
    if is_pr:
        logger.info("PR : %s -> %s" % (branch, target))
    else:
        logger.info("BRANCH : %s" % branch)
    logger.info("COMMIT_ID : %s" % commit_id[:7])
    logger.info("NAME_PREFIX : %s" % name_prefix)
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
