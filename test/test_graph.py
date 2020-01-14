import os
import subprocess

import pytest

from dmake import cli, common, core, deepobuild

graph_test_list = [
    ('shell', 'test-web'),
    ('build', 'test-web'),
    ('test', 'test-e2e'),
    ('test', 'test-web2'),
    ('test', '*'),
    ('run', 'test-web2'),
    ('run', 'test-e2e'),
    ('deploy', 'test-k8s'),
    ('deploy', 'test-e2e'),
    ('deploy', '*'),
]
def generate_resources_graph(test_list = graph_test_list):
    path = os.path.dirname(__file__)
    for command, service in test_list:
        expected_dot_path = os.path.join(path, 'test-resources/graph.{command}.{service}.gv'.format(command=command, service=service))
        subprocess.call([
            'dmake',
            '--debug-graph-and-exit',
            '--debug-graph-output-filename={}'.format(expected_dot_path),
            command, service
        ], cwd=path)

@pytest.mark.parametrize("command,service", graph_test_list)
def test_graph(command, service):
    deepobuild.reset()

    args = cli.argparser.parse_args([command, service])
    common.init(args)

    common.sub_dir = 'test'  # to test '*' for only 'test/'
    common.generate_dot_graph = True
    common.exit_after_generate_dot_graph = True
    common.dot_graph_filename = None
    dot = core.make(args)

    path = os.path.dirname(__file__)
    expected_dot_path = os.path.join(path, 'test-resources/graph.{command}.{service}.gv'.format(command=command, service=service))
    with open(expected_dot_path, "r") as f:
        # dot.source and dot.render() to file differ with extra '\n'
        expected_dot_source = f.read().rstrip('\n')

    assert expected_dot_source == dot.source, (
        "Unexpected `dmake {command} {service}` graph."
        "Update it with:"
        "\npushd '{path}' && dmake --debug-graph-and-exit --debug-graph-output-filename='{expected_dot_path}' {command} '{service}' && popd"
        "\nOr rebuild them all:"
        "\nmake -C {path} rebuild_graphs".format(path=path, command=command, service=service, expected_dot_path=expected_dot_path)
    )
