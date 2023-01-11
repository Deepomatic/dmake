import sys
import os
import argcomplete
import argparse
import dmake.commands as commands
import dmake.core as core
import dmake.common as common


def check_is_git_repo():
    try:
        common.run_shell_command('git rev-parse --abbrev-ref HEAD')
        return True
    except common.ShellError as e:
        common.logger.error("Current directory is not a Git repository:\n%s" % str(e))
        return False


def add_argument(parsers, *args, **kwargs):
    for parser in parsers:
        parser.add_argument(*args, **kwargs)


def completion_action(args):
    print(argcomplete.shellcode(['dmake'], shell=args.shell))


# Find root
try:
    root_dir, sub_dir = common.find_repo_root()
except common.ShellError as e:
    common.logger.error("Current directory is not a Git repository:\n%s" % str(e))
    sys.exit(1)
os.chdir(root_dir)

# Defines command line parser
argparser = argparse.ArgumentParser(prog='dmake')

argparser.add_argument('--debug-graph', default=False, action='store_true', help="Generate dmake steps DOT graph for debug purposes.")
argparser.add_argument('--debug-graph-and-exit', default=False, action='store_true', help="Generate dmake steps DOT graph for debug purposes then exit.")
argparser.add_argument('--debug-graph-group-by', default='command', choices=['command', 'height'], help="Group nodes by <> in generated DOT graph.")
argparser.add_argument('--debug-graph-pretty', '--no-debug-graph-pretty', default=True, action=common.FlagBooleanAction, help="Pretty or raw output for debug graph.")
argparser.add_argument('--debug-graph-output-filename', help="The generated DOT graph filename. Defaults to 'dmake-services.debug.{group_by}.gv'")
argparser.add_argument('--debug-graph-output-format', default='png', help="The generated DOT graph format (`png`, `svg`, `pdf`, ...).")

subparsers = argparser.add_subparsers(dest='cmd', title='Commands')
subparsers.required = True

parser_test    = subparsers.add_parser('test', help="Launch tests for the whole repo or, if specified, an app or one of its services.")
parser_build   = subparsers.add_parser('build', help="Launch the build for the whole repo or, if specified, an app or one of its services.")
parser_run     = subparsers.add_parser('run', help="Launch the application or only one of its services.")
parser_stop    = subparsers.add_parser('stop', help="Stop the containers started by dmake for the current repository and branch. Usually by 'dmake run', but can also be useful to cleanup aborted executions of dmake.")
parser_shell   = subparsers.add_parser('shell', help="Run a shell session withing a docker container with the environment set up for a given service.")
parser_deploy  = subparsers.add_parser('deploy', help="Deploy specified apps and services.")
parser_release = subparsers.add_parser('release', help="Create a Github release (with changelog) of the app based on a previously created git tag.")
parser_graph   = subparsers.add_parser('graph', help="Generate a visual graph of the app services dependencies (dot/graphviz format).")
parser_generate_doc = subparsers.add_parser('generate-doc', help="Generate DMake documentation.")


# "service" argument
for parser in [parser_deploy]:
    parser.add_argument("service", nargs='?', default='*', help="Apply command to the full repository or, if specified, to the app/service. When specifying a service, you may skip the app if there is no ambiguity, otherwise, you need to specify 'app/service'.").completer = core.service_completer
for parser in [parser_test]:
    parser.add_argument("service", nargs='?', default='*', help="Apply command to the full repository (`*`) or to changed services (`+`), or the specified app/service. When specifying a service, you may skip the app if there is no ambiguity, otherwise, you need to specify 'app/service'.").completer = core.service_completer
for parser in [parser_shell]:
    parser.add_argument("service", nargs='?', default='.', help="Run a shell session withing the docker base image for the given service. You may skip the app if there is no ambiguity, otherwise, you need to specify 'app/service'.").completer = core.service_completer
for parser in [parser_run]:
    parser.add_argument("service", help="Run an application or a service. When specifying a service, you may skip the app if there is no ambiguity, otherwise, you need to specify 'app/service'.").completer = core.service_completer
for parser in [parser_build]:
    parser.add_argument("service", help="Build an application or a service. Use `+` to build only changed services. When specifying a service, you may skip the app if there is no ambiguity, otherwise, you need to specify 'app/service'.").completer = core.service_completer

parser_shell.add_argument("-c", '--command', help="Pass to `docker run` specified command instead of `docker.command` defined in `dmake.yml` (default: `bash`).")
add_argument([parser_shell, parser_run, parser_test, parser_deploy],
             "-d", "--dependencies", "--no-dependencies", "-s", "--standalone", required=False, default=True, dest='with_dependencies', action=common.DependenciesBooleanAction,
             help="These options control if dependencies are run/tested/deployed. By default, the service is run/tested/deployed alongside its dependencies (service and link dependencies), recursively.")
add_argument([parser_shell, parser_run, parser_test, parser_deploy, parser_stop], "-b", "--branch", required=False, default=None, help="Overwrite the git branch name used to select the dmake environment")

parser_run.add_argument("--docker-links-volumes-persistence", "--no-docker-links-volumes-persistence", required=False, default=False, dest='with_docker_links_volumes_persistence', action=common.FlagBooleanAction, help="Control persistence of docker-links volumes (default: non-persistent (for dmake run)).")

parser_release.add_argument("app", help="DMake app to release (must match the github project name under github owner)")
parser_release.add_argument('-t', '--tag', nargs='?', help="The git tag from which the release will be created.")

parser_generate_doc.add_argument("kind", choices=['usage', 'format', 'example'])

parser_graph.add_argument('--output', default='dmake-services.gv', help="The generated DOT graph filename.")
parser_graph.add_argument('--format', default='png', help="The generated DOT graph format (`png`, `svg`, `pdf`, ...).")

parser_test.set_defaults(func=core.make)
parser_run.set_defaults(func=core.make)
parser_build.set_defaults(func=core.make)
parser_stop.set_defaults(func=commands.stop.entry_point)
parser_shell.set_defaults(func=core.make)
parser_deploy.set_defaults(func=core.make)
parser_release.set_defaults(func=commands.release.entry_point)
parser_graph.set_defaults(func=commands.graph.entry_point)
parser_generate_doc.set_defaults(func=commands.generate_doc.entry_point)



# Shell completion
parser_completion = subparsers.add_parser('completion',
                                          help="Output shell completion code for bash (may work for zsh)",
                                          formatter_class=argparse.RawDescriptionHelpFormatter,
                                          description="""
This command can generate shell autocompletions. e.g.

    $ dmake completion

Can be sourced as such

    $ source <(dmake completion)

./install.sh should have already installed everything in:
- ${HOME}/.dmake/completion.bash.inc
- ${HOME}/.dmake/config.sh
- ${HOME}/.bashrc
""",
                                          )
parser_completion.add_argument("shell", nargs='?', default='bash', choices=['bash'], help="Shell to emit completion for")
parser_completion.set_defaults(func=completion_action)
