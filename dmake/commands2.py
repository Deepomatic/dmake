import os
import uuid

import dmake.common as common
from dmake.common import DMakeException

tag_push_error_msg = "Unauthorized to push the current state of deployment to git server. If the repository belongs to you, please check that the credentials declared in the DMAKE_JENKINS_SSH_AGENT_CREDENTIALS and DMAKE_JENKINS_HTTP_CREDENTIALS allow you to write to the repository."

###############################################################################

def make_path_unique_per_variant(path, service_name):
    """If multi variant: prefix filename with `<variant>-`"""
    service_name_parts = service_name.split(':')
    if len(service_name_parts) == 2:
        variant = service_name_parts[1]
        head, tail = os.path.split(path)
        path = os.path.join(head, '%s-%s' % (variant, tail))
    return path

###############################################################################

def get_cobertura_tests_results_dir():
    return os.path.join(common.relative_cache_dir, 'cobertura_tests_results')

###############################################################################

def generate_pipeline_command(context, cmd, **kwargs):
    if cmd == "stage":
        name = kwargs['name'].replace("'", "\\'")
        context.write_line('')
        if kwargs['concurrency'] is not None and kwargs['concurrency'] > 1:
            raise DMakeException("Unsupported stage concurrency: %s > 1" % kwargs['concurrency'])
        context.write_line("stage('%s') {" % name)
        context.indent()
    elif cmd == "stage_end":
        context.outdent()
        context.write_line("}")
    elif cmd == "lock":
        assert(kwargs['label'] == 'GPUS')
        context.write_line("lock(label: 'GPUS', quantity: 1, variable: 'DMAKE_GPU') {")
        context.indent()
    elif cmd == "lock_end":
        context.outdent()
        context.write_line("}")
    elif cmd == "timeout":
        time = kwargs['time']
        context.write_line("timeout(time: %s, unit: 'SECONDS') {" % time)
        context.indent()
    elif cmd == "timeout_end":
        context.outdent()
        context.write_line("}")
    elif cmd == "echo":
        message = kwargs['message'].replace("'", "\\'")
        context.write_line("echo '%s'" % message)
    elif cmd == "sh":
        commands = kwargs['shell']
        if common.is_string(commands):
            commands = [commands]
        commands = [common.escape_cmd(c) for c in commands]
        if len(commands) == 0:
            return
        if len(commands) == 1:
            context.write_line('sh("%s")' % commands[0])
        else:
            context.write_line('parallel (')
            commands_list = []
            for c in enumerate(commands):
                commands_list.append("cmd%d: { sh('%s') }" % c)
            context.write_line(','.join(commands_list))
            context.write_line(')')
    elif cmd == "read_sh":
        file_output = os.path.join(common.cache_dir, "output_%s" % uuid.uuid4())
        context.write_line("sh('%s > %s')" % (kwargs['shell'], file_output))
        context.write_line("env.%s = readFile '%s'" % (kwargs['var'], file_output))
        if kwargs['fail_if_empty']:
            context.write_line("sh('if [ -z \"${%s}\" ]; then exit 1; fi')" % kwargs['var'])
    elif cmd == "global_env":
        context.write_line('env.%s = "%s"' % (kwargs['var'], kwargs['value']))
    elif cmd == "with_env":
        context.write_line('withEnv([')
        context.indent()
        environment = kwargs['value']
        for element in environment[:-1]:
            context.write_line('"%s=%s",' % (element[0], element[1]))
        last_element = environment[-1]
        context.write_line('"%s=%s"]) {' % (last_element[0], last_element[1]))
    elif cmd == "with_env_end":
        context.outdent()
        context.write_line('} // WithEnv end')
    elif cmd == "git_tag":
        if common.repo_url is not None:
            context.write_line("sh('git tag --force %s')" % kwargs['tag'])
            context.write_line('try {')
            context.indent()
            if common.repo_url.startswith('https://') or common.repo_url.startswith('http://'):
                i = common.repo_url.find(':')
                prefix = common.repo_url[:i]
                host = common.repo_url[(i + 3):]
                context.write_line("withCredentials([[$class: 'UsernamePasswordMultiBinding', credentialsId: env.DMAKE_JENKINS_HTTP_CREDENTIALS, usernameVariable: 'GIT_USERNAME', passwordVariable: 'GIT_PASSWORD']]) {")
                context.indent()
                context.write_line('try {')
                context.write_line("""  sh("git push --force '%s://${GIT_USERNAME}:${GIT_PASSWORD}@%s' refs/tags/%s")""" % (prefix, host, kwargs['tag']))
                context.write_line('} catch(error) {')
                context.write_line("""  sh('echo "%s"')""" % tag_push_error_msg.replace("'", "\\'"))
                context.write_line('}')
                error_msg = "Define 'User/Password' credentials and set their ID in the 'DMAKE_JENKINS_HTTP_CREDENTIALS' environment variable to be able to build and deploy only changed parts of the app."
                context.outdent()
                context.write_line('}')
            else:
                context.write_line("sh('git push --force %s refs/tags/%s')" % (common.remote, kwargs['tag']))
                error_msg = tag_push_error_msg
            context.outdent()
            context.write_line('} catch(error) {')
            context.write_line("""  sh('echo "%s"')""" % error_msg.replace("'", "\\'"))
            context.write_line('}')
    elif cmd == "junit":
        container_report = os.path.join(kwargs['mount_point'], kwargs['report'])
        host_report = os.path.join(common.relative_cache_dir, 'tests_results', str(uuid.uuid4()), kwargs['service_name'].replace(':', '-'), kwargs['report'])
        context.write_line('''sh('dmake_test_get_results "%s" "%s" "%s"')''' % (kwargs['service_name'], container_report, host_report))
        context.write_line("junit keepLongStdio: true, testResults: '%s'" % host_report)
        context.write_line('''sh('rm -rf "%s"')''' % host_report)
    elif cmd == "cobertura":
        # coberturaPublisher plugin only supports one step, so we delay generating it, and make it get all reports
        container_report = os.path.join(kwargs['mount_point'], kwargs['report'])
        host_report = os.path.join(get_cobertura_tests_results_dir(), str(uuid.uuid4()), kwargs['service_name'].replace(':', '-'), kwargs['report'])
        if not host_report.endswith('.xml'):
            raise DMakeException("`cobertura_report` must end with '.xml' in service '%s'" % kwargs['service_name'])
        context.write_line('''sh('dmake_test_get_results "%s" "%s" "%s"')''' % (kwargs['service_name'], container_report, host_report))
        #self.emit_cobertura = True
    elif cmd == "publishHTML":
        container_html_directory = os.path.join(kwargs['mount_point'], kwargs['directory'])
        host_html_directory = os.path.join(common.cache_dir, 'tests_results', str(uuid.uuid4()), kwargs['service_name'].replace(':', '-'), kwargs['directory'])
        context.write_line('''sh('dmake_test_get_results "%s" "%s" "%s"')''' % (kwargs['service_name'], container_html_directory, host_html_directory))
        context.write_line("publishHTML(target: [allowMissing: false, alwaysLinkToLastBuild: true, keepAll: false, reportDir: '%s', reportFiles: '%s', reportName: '%s'])" % (host_html_directory, kwargs['index'], kwargs['title'].replace("'", "\'")))
        context.write_line('''sh('rm -rf "%s"')''' % host_html_directory)
    else:
        raise DMakeException("Unknown command %s" % cmd)

###############################################################################

def generate_shell_command(context, cmd, **kwargs):
    if cmd == "stage":
        context.write_line("")
        context.write_line("echo -e '\n## %s ##'" % kwargs['name'])
    elif cmd == "stage_end":
        pass
    elif cmd == "lock":
        # lock not supported with bash
        pass
    elif cmd == "lock_end":
        pass
    elif cmd == "timeout":
        # timeout not supported with bash
        pass
    elif cmd == "timeout_end":
        pass
    elif cmd == "echo":
        message = kwargs['message'].replace("'", "\\'")
        context.write_line("echo '%s'" % message)
    elif cmd == "sh":
        commands = kwargs['shell']
        if common.is_string(commands):
            commands = [commands]
        for c in commands:
            context.write_line("%s" % c)
    elif cmd == "read_sh":
        context.write_line("%s=`%s`" % (kwargs['var'], kwargs['shell']))
        if kwargs['fail_if_empty']:
            context.write_line("if [ -z \"${%s}\" ]; then exit 1; fi" % kwargs['var'])
    elif cmd == "global_env":
        context.write_line('%s="%s"' % (kwargs['var'], kwargs['value'].replace('"', '\\"')))
        context.write_line('export %s' % kwargs['var'])
    elif cmd == "with_env":
        environment = kwargs['value']
        for element in environment:
            context.write_line('%s="%s"' % (element[0], element[1].replace('"', '\\"')))
            context.write_line('export %s' % element[0])
    elif cmd == "with_env_end":
        pass
    elif cmd == "git_tag":
        context.write_line('git tag --force %s' % kwargs['tag'])
        context.write_line('git push --force %s refs/tags/%s || echo %s' % (common.remote, kwargs['tag'], tag_push_error_msg))
    elif cmd == "junit" or cmd == "cobertura":
        container_report = os.path.join(kwargs['mount_point'], kwargs['report'])
        host_report = make_path_unique_per_variant(kwargs['report'], kwargs['service_name'])
        context.write_line('dmake_test_get_results "%s" "%s" "%s"' % (kwargs['service_name'], container_report, host_report))
    elif cmd == "publishHTML":
        container_html_directory = os.path.join(kwargs['mount_point'], kwargs['directory'])
        host_html_directory = make_path_unique_per_variant(kwargs['directory'], kwargs['service_name'])
        context.write_line('dmake_test_get_results "%s" "%s" "%s"' % (kwargs['service_name'], container_html_directory, host_html_directory))
    else:
            raise DMakeException("Unknown command %s" % cmd)

###############################################################################

def validate_command(cmd, **args):
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
    elif cmd == "global_env":
        check_cmd(args, ['var', 'value'])
    elif cmd == "with_env":
        check_cmd(args, ['value'])
    elif cmd == "with_env_end":
        pass
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

###############################################################################

class WriteContext(object):
    """ A Class that helds the writing context and knows how to wirte a line
    """

    def __init__(self, file):
        self.file = file
        self.indent_level = 0

    def write_line(self, data):
        if len(data) > 0:
            self.file.write('  ' * self.indent_level)
        self.file.write(data + '\n')

    def indent(self):
        self.indent_level += 1

    def outdent(self):
        self.indent_level -= 1

###############################################################################

class CommandNode(object):
    """ A node
    """
    def __init__(self, generate_cmd):
        self.commands = []
        self.generate_command = generate_cmd

    def _header(self, context):
        """
        Add in this method the commands to be generated at the beginning of each node
        """
        pass

    def _trailer(self, context):
        """
        Add in this method the commands to be generated at the end of each node
        """
        pass

    def generate_commands(self, context):
        self._header(context)
        for cmd, kwargs in self.commands:
            self.generate_command(context, cmd, **kwargs)
        self._trailer(context)


    def try_append(self, cmd, prepend = False, **args ):
        validate_command(cmd, **args)
        cmd = (cmd, args)
        if prepend:
            self.commands.insert(0, cmd)
        else:
            self.commands.append(cmd)

    def append_many(self, commands):
        for cmd in commands:
            self.commands.append(cmd)

###############################################################################

#class BashCommandNode(CommandNode):
#    """ A node that knows what to write in case of bash
#    """
#    def __init__(self):
#         CommandNode.__init__(self)
#
#    def _header(self, context):
#        """
#        The commands to be generated at the beginning of each bash node
#        """
#        pass
#
#    def _trailer(self, context):
#        """
#         The commands to be generated at the end of each bash node
#        """
#        pass
#
###############################################################################

#class PipelineCommandNode(CommandNode):
#    """ A node that knows what to write a pipeline node
#    """
#    def __init__(self):
#        CommandNode.__init__(self)
#
#    def _header(self, context):
#        """
#        The commands to be generated at the beginning of each pipeline node
#        """
#        pass
#
#    def _trailer(self, context):
#        """
#         The commands to be generated at the end of each pipeline node
#        """
#        pass
#
###############################################################################

class RootCommandNode(CommandNode):
    """ A node that knows what to write at the root level of a file
    """
    def __init__(self, generate_cmd, use_pipeline):
        CommandNode.__init__(self, generate_cmd)
        self.use_pipeline = use_pipeline
    def _header(self, context):
        """
        The commands to be generated at the beginning of the file
        """

        if self.use_pipeline:
            if common.build_description is not None:
                context.write_line("currentBuild.description = '%s'" % common.build_description.replace("'", "\\'"))
        else:
            context.write_line('test "${DMAKE_DEBUG}" = "1" && set -x')
            context.write_line('set -e')

        self.generate_command(context, 'global_env', var="REPO", value=common.repo)
        self.generate_command(context, 'global_env', var="COMMIT", value=common.commit_id)
        self.generate_command(context, 'global_env', var="BUILD", value=common.build_id)
        self.generate_command(context, 'global_env', var="BRANCH", value=common.branch)
        self.generate_command(context, 'with_env', value=[("DMAKE_TMP_DIR", common.tmp_dir)])
        # check DMAKE_TMP_DIR still exists: detects unsupported jenkins reruns: clear error
        self.generate_command(context, 'sh', shell='dmake_check_tmp_dir')

        if self.use_pipeline:
            context.write_line('try {')
            context.indent()
        else:
            pass

    def _trailer(self, context):
        """
        The commands to be generated at the end of the file
        """

        if self.use_pipeline:
            if True:
                cobertura_tests_results_dir = get_cobertura_tests_results_dir()
                context.write_line("step([$class: 'CoberturaPublisher', autoUpdateHealth: false, autoUpdateStability: false, coberturaReportFile: '%s/**/*.xml', failUnhealthy: false, failUnstable: false, maxNumberOfBuilds: 0, onlyStable: false, sourceEncoding: 'ASCII', zoomCoverageChart: false])" % (cobertura_tests_results_dir))
                context.write_line('''sh('rm -rf "%s"')''' % cobertura_tests_results_dir)

            # try end
            context.indent_level -= 1
            context.write_line('}')
            context.write_line('catch (error) {')
            context.write_line('  if ( env.DMAKE_PAUSE_ON_ERROR_BEFORE_CLEANUP == "1" ) {')
            context.write_line('    slackSend channel: "#jenkins-dmake", message: "This jenkins build requires your attention: <${env.BUILD_URL}/console|${env.JOB_NAME} ${env.BUILD_NUMBER}>"')
            context.write_line("    input message: 'An error occurred. DMake will stop and clean all the running containers upon any answer.'")
            context.write_line('  }')
            context.write_line('  throw error')
            context.write_line('}')
            context.write_line('finally {')
            context.write_line('  sh("dmake_clean")')
            context.write_line('}')
        else:
            pass
        self.generate_command(context, 'with_env_end')

###############################################################################

class CommandsManager(object):
    """ This class that handles command nodes and ouputs them to in a specific order.
        The script will be written to the output in this order:
            root.header()
            for each node in nodes:
                node.header()
                for each cmd in node.commands:
                    cmd
                node.trailer()
            root.trailer()
       Use this scheme to put the code you want to generate in the proper place.
    """

    def __init__(self, use_pipeline = True):
        self.use_pipeline = common.use_pipeline
        if self.use_pipeline:
            self.root = RootCommandNode(generate_pipeline_command, True)
        else:
            self.root = RootCommandNode(generate_shell_command, False)
        self.nodes = []

    def make_node(self):
        node = None
        if self.use_pipeline:
            node = CommandNode(generate_pipeline_command)
        else:
            node = CommandNode(generate_shell_command)
        return node

    def add_node(self, node):
        self.nodes.append(node)

    def generate_script(self, file_name):
        with open(file_name, "w") as file:
            context = WriteContext(file)
            self.root._header(context)
            for node in self.nodes:
                node.generate_commands(context)
            self.root._trailer(context)
