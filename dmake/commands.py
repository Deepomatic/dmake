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

class WriteContext(object):

    def __init__(self, file):
        self.file = file
        self.indent_level = 0
        self.emit_cobertura = False

    def write_line(self, data):
        if len(data) > 0:
            self.file.write('  ' * self.indent_level)
        self.file.write(data + '\n')

    def generate_command(self, cmd, **kwargs):
        if common.use_pipeline:
            self.generate_command_pipeline(cmd, **kwargs)
        else:
            self.generate_command_bash(cmd, **kwargs)

    def generate_command_pipeline(self, cmd, **kwargs):
        if cmd == "try":
            self.write_line('try {')
            self.indent_level += 1
        elif cmd == "try_end":
            self.indent_level -= 1
            self.write_line('}')
        elif cmd == "stage":
            name = kwargs['name'].replace("'", "\\'")
            self.write_line('')
            if kwargs['concurrency'] is not None and kwargs['concurrency'] > 1:
                raise DMakeException("Unsupported stage concurrency: %s > 1" % kwargs['concurrency'])
            self.write_line("stage('%s') {" % name)
            self.indent_level += 1
        elif cmd == "stage_end":
            self.indent_level -= 1
            self.write_line("}")
        elif cmd == "lock":
            assert(kwargs['label'] == 'GPUS')
            self.write_line("lock(label: 'GPUS', quantity: 1, variable: 'DMAKE_GPU') {")
            self.indent_level += 1
        elif cmd == "lock_end":
            self.indent_level -= 1
            self.write_line("}")
        elif cmd == "timeout":
            time = kwargs['time']
            self.write_line("timeout(time: %s, unit: 'SECONDS') {" % time)
            self.indent_level += 1
        elif cmd == "timeout_end":
            self.indent_level -= 1
            self.write_line("}")
        elif cmd == "echo":
            message = kwargs['message'].replace("'", "\\'")
            self.write_line("echo '%s'" % message)
        elif cmd == "sh":
            commands = kwargs['shell']
            if common.is_string(commands):
                commands = [commands]
            commands = [common.escape_cmd(c) for c in commands]
            if len(commands) == 0:
                return
            if len(commands) == 1:
                self.write_line('sh("%s")' % commands[0])
            else:
                self.write_line('parallel (')
                commands_list = []
                for c in enumerate(commands):
                    commands_list.append("cmd%d: { sh('%s') }" % c)
                self.write_line(','.join(commands_list))
                self.write_line(')')
        elif cmd == "read_sh":
            file_output = os.path.join(common.cache_dir, "output_%s" % uuid.uuid4())
            self.write_line("sh('%s > %s')" % (kwargs['shell'], file_output))
            self.write_line("env.%s = readFile '%s'" % (kwargs['var'], file_output))
            if kwargs['fail_if_empty']:
                self.write_line("sh('if [ -z \"${%s}\" ]; then exit 1; fi')" % kwargs['var'])
        elif cmd == "global_env":
            self.write_line('env.%s = "%s"' % (kwargs['var'], kwargs['value']))
        elif cmd == "with_env":
            self.write_line('withEnv([')
            self.indent_level += 1
            environment = kwargs['value']
            for element in environment[:-1]:
                self.write_line('"%s=%s",' % (element[0], element[1]))
            last_element = environment[-1]
            self.write_line('"%s=%s"]) {' % (last_element[0], last_element[1]))
        elif cmd == "with_env_end":
            self.indent_level -= 1
            self.write_line('} // WithEnv end')
        elif cmd == "git_tag":
            if common.repo_url is not None:
                self.write_line("sh('git tag --force %s')" % kwargs['tag'])
                self.write_line('try {')
                self.indent_level += 1
                if common.repo_url.startswith('https://') or common.repo_url.startswith('http://'):
                    i = common.repo_url.find(':')
                    prefix = common.repo_url[:i]
                    host = common.repo_url[(i + 3):]
                    self.write_line("withCredentials([[$class: 'UsernamePasswordMultiBinding', credentialsId: env.DMAKE_JENKINS_HTTP_CREDENTIALS, usernameVariable: 'GIT_USERNAME', passwordVariable: 'GIT_PASSWORD']]) {")
                    self.indent_level += 1
                    self.write_line('try {')
                    self.write_line("""  sh("git push --force '%s://${GIT_USERNAME}:${GIT_PASSWORD}@%s' refs/tags/%s")""" % (prefix, host, kwargs['tag']))
                    self.write_line('} catch(error) {')
                    self.write_line("""  sh('echo "%s"')""" % tag_push_error_msg.replace("'", "\\'"))
                    self.write_line('}')
                    error_msg = "Define 'User/Password' credentials and set their ID in the 'DMAKE_JENKINS_HTTP_CREDENTIALS' environment variable to be able to build and deploy only changed parts of the app."
                    self.indent_level -= 1
                    self.write_line('}')
                else:
                    self.write_line("sh('git push --force %s refs/tags/%s')" % (common.remote, kwargs['tag']))
                    error_msg = tag_push_error_msg
                self.indent_level -= 1
                self.write_line('} catch(error) {')
                self.write_line("""  sh('echo "%s"')""" % error_msg.replace("'", "\\'"))
                self.write_line('}')
        elif cmd == "junit":
            container_report = os.path.join(kwargs['mount_point'], kwargs['report'])
            host_report = os.path.join(common.relative_cache_dir, 'tests_results', str(uuid.uuid4()), kwargs['service_name'].replace(':', '-'), kwargs['report'])
            self.write_line('''sh('dmake_test_get_results "%s" "%s" "%s"')''' % (kwargs['service_name'], container_report, host_report))
            self.write_line("junit keepLongStdio: true, testResults: '%s'" % host_report)
            self.write_line('''sh('rm -rf "%s"')''' % host_report)
        elif cmd == "cobertura":
            # coberturaPublisher plugin only supports one step, so we delay generating it, and make it get all reports
            container_report = os.path.join(kwargs['mount_point'], kwargs['report'])
            host_report = os.path.join(get_cobertura_tests_results_dir(), str(uuid.uuid4()), kwargs['service_name'].replace(':', '-'), kwargs['report'])
            if not host_report.endswith('.xml'):
                raise DMakeException("`cobertura_report` must end with '.xml' in service '%s'" % kwargs['service_name'])
            self.write_line('''sh('dmake_test_get_results "%s" "%s" "%s"')''' % (kwargs['service_name'], container_report, host_report))
            self.emit_cobertura = True
        elif cmd == "publishHTML":
            container_html_directory = os.path.join(kwargs['mount_point'], kwargs['directory'])
            host_html_directory = os.path.join(common.cache_dir, 'tests_results', str(uuid.uuid4()), kwargs['service_name'].replace(':', '-'), kwargs['directory'])
            self.write_line('''sh('dmake_test_get_results "%s" "%s" "%s"')''' % (kwargs['service_name'], container_html_directory, host_html_directory))
            self.write_line("publishHTML(target: [allowMissing: false, alwaysLinkToLastBuild: true, keepAll: false, reportDir: '%s', reportFiles: '%s', reportName: '%s'])" % (host_html_directory, kwargs['index'], kwargs['title'].replace("'", "\'")))
            self.write_line('''sh('rm -rf "%s"')''' % host_html_directory)
        else:
            raise DMakeException("Unknown command %s" % cmd)

    def generate_command_bash(self, cmd, **kwargs):
        if cmd == "try":
            pass
        elif cmd == "try_end":
            pass
        elif cmd == "stage":
            self.write_line("\n")
            self.write_line("echo -e '\n## %s ##'\n" % kwargs['name'])
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
            self.write_line("echo '%s'\n" % message)
        elif cmd == "sh":
            commands = kwargs['shell']
            if common.is_string(commands):
                commands = [commands]
            for c in commands:
                self.write_line("%s\n" % c)
        elif cmd == "read_sh":
            self.write_line("%s=`%s`\n" % (kwargs['var'], kwargs['shell']))
            if kwargs['fail_if_empty']:
                self.write_line("if [ -z \"${%s}\" ]; then exit 1; fi\n" % kwargs['var'])
        elif cmd == "global_env":
            self.write_line('%s="%s"\n' % (kwargs['var'], kwargs['value'].replace('"', '\\"')))
            self.write_line('export %s\n' % kwargs['var'])
        elif cmd == "with_env":
            environment = kwargs['value']
            for element in environment:
                self.write_line('%s="%s"\n' % (element[0], element[1].replace('"', '\\"')))
                self.write_line('export %s\n' % element[0])
        elif cmd == "with_env_end":
            pass
        elif cmd == "git_tag":
            self.write_line('git tag --force %s\n' % kwargs['tag'])
            self.write_line('git push --force %s refs/tags/%s || echo %s\n' % (common.remote, kwargs['tag'], tag_push_error_msg))
        elif cmd == "junit" or cmd == "cobertura":
            container_report = os.path.join(kwargs['mount_point'], kwargs['report'])
            host_report = make_path_unique_per_variant(kwargs['report'], kwargs['service_name'])
            self.write_line('dmake_test_get_results "%s" "%s" "%s"\n' % (kwargs['service_name'], container_report, host_report))
        elif cmd == "publishHTML":
            container_html_directory = os.path.join(kwargs['mount_point'], kwargs['directory'])
            host_html_directory = make_path_unique_per_variant(kwargs['directory'], kwargs['service_name'])
            self.write_line('dmake_test_get_results "%s" "%s" "%s"\n' % (kwargs['service_name'], container_html_directory, host_html_directory))
        else:
            raise DMakeException("Unknown command %s" % cmd)

###############################################################################

class CommandNode(object):

    def __init__(self):
        self.commands = []

    def generate_command_pipeline(self, context):
        if common.build_description is not None:
            context.write_line("currentBuild.description = '%s'" % common.build_description.replace("'", "\\'"))

        context.generate_command_pipeline('with_env', value=[("DMAKE_TMP_DIR", common.tmp_dir)])

        context.write_line('try {')
        context.indent_level += 1

        # check DMAKE_TMP_DIR still exists: detects unsupported jenkins reruns: clear error
        context.generate_command_pipeline('sh', shell='dmake_check_tmp_dir')

        for cmd, kwargs in self.commands:
            context.generate_command_pipeline(cmd, **kwargs)

        if context.emit_cobertura:
            cobertura_tests_results_dir = get_cobertura_tests_results_dir()
            self.write_line("step([$class: 'CoberturaPublisher', autoUpdateHealth: false, autoUpdateStability: false, coberturaReportFile: '%s/**/*.xml', failUnhealthy: false, failUnstable: false, maxNumberOfBuilds: 0, onlyStable: false, sourceEncoding: 'ASCII', zoomCoverageChart: false])" % (cobertura_tests_results_dir()))
            self.write_line('''sh('rm -rf "%s"')''' % cobertura_tests_results_dir())

        # try end
        context.indent_level -= 1
        self.write_line('}')
        self.write_line('catch (error) {')
        self.write_line('  if ( env.DMAKE_PAUSE_ON_ERROR_BEFORE_CLEANUP == "1" ) {')
        self.write_line('    slackSend channel: "#jenkins-dmake", message: "This jenkins build requires your attention: <${env.BUILD_URL}/console|${env.JOB_NAME} ${env.BUILD_NUMBER}>"')
        self.write_line("    input message: 'An error occurred. DMake will stop and clean all the running containers upon any answer.'")
        self.write_line('  }')
        self.write_line('  throw error')
        self.write_line('}')
        self.write_line('finally {')
        self.write_line('  sh("dmake_clean")')
        self.write_line('}')

        # FIXME: Find a better way to close the withEnv
        self.indent_level -= 1
        self.write_line('} // withEnv end')

    def generate_command_bash(self, context):
        context.write_line('test "${DMAKE_DEBUG}" = "1" && set -x\n')
        context.write_line('set -e\n')
        for cmd, kwargs in self.commands:
            context.generate_command_bash(cmd, **kwargs)

###############################################################################

class Commands(object):

    def __init__(self):
        self.nodes = [CommandNode()]

    def add_command(self, position, cmd, prepend=False):
        last_node = self.nodes[-1]
        if prepend:
            last_node.commands.insert(0, cmd)
        else:
            last_node.commands.append(cmd)

    def generate_script(self, file_name):
        with open(file_name, "w") as file:
            context = WriteContext(file)

            context.generate_command('global_env', var="REPO", value=common.repo)
            context.generate_command('global_env', var="COMMIT", value=common.commit_id)
            context.generate_command('global_env', var="BUILD", value=common.build_id)
            context.generate_command('global_env', var="BRANCH", value=common.branch)

            for node in self.nodes:
                if common.use_pipeline:
                    node.generate_command_pipeline(context)
                else:
                    node.generate_command_bash(context)
