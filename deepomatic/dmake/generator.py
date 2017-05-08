import os
import common

tag_push_error_msg = "Unauthorized to push the current state of deployment to git server. If the repository belongs to you, please check that the credentials declared in the DMAKE_JENKINS_SSH_AGENT_CREDENTIALS and DMAKE_JENKINS_HTTP_CREDENTIALS allow you to write to the repository."

###############################################################################

def generate(file_name, cmds):
    with open(file_name, "w") as file:
        if common.use_pipeline:
            generate_jenkins_pipeline(file, cmds)
        else:
            generate_bash(file, cmds)

###############################################################################

def generate_jenkins_pipeline(file, cmds):
    if common.build_description is not None:
        file.write("currentBuild.description = '%s'\n" % common.build_description.replace("'", "\\'"))
    file.write('try {\n')

    for cmd, kwargs in cmds:
        if cmd == "stage":
            name = kwargs['name'].replace("'", "\\'")
            if kwargs['concurrency'] is not None:
                file.write("stage concurrency: %s, name: '%s'\n" % (str(kwargs['concurrency']), name))
            else:
                file.write("stage '%s'\n" % name)
        elif cmd == "sh":
            commands = kwargs['shell']
            if common.is_string(commands):
                commands = [commands]
            commands = [c.replace("'", "\\'")
                         .replace("$", "\\$") for c in commands]
            if len(commands) == 0:
                return
            if len(commands) == 1:
                file.write("sh('%s')\n" % commands[0])
            else:
                file.write('parallel (\n')
                commands_list = []
                for c in enumerate(commands):
                    commands_list.append("cmd%d: { sh('%s') }" % c)
                file.write(',\n'.join(commands_list))
                file.write(')\n')
        elif cmd == "read_sh":
            file_output = os.path.join(common.root_dir, ".dmake", "output_%d" % kwargs['id'])
            file.write("sh('%s > %s')\n" % (kwargs['shell'], file_output))
            file.write("env.%s = readFile '%s'\n" % (kwargs['var'], file_output));
            if kwargs['fail_if_empty']:
                file.write("sh('if [ -z \"${%s}\" ]; then exit 1; fi')\n" % kwargs['var'])
        elif cmd == "env":
            file.write('env.%s = "%s"\n' % (kwargs['var'], kwargs['value']))
        elif cmd == "git_tag":
            if common.repo_url is not None:
                file.write("sh('git tag --force %s')\n" % kwargs['tag'])
                file.write('try {\n')
                if common.repo_url.startswith('https://') or common.repo_url.startswith('http://'):
                    i = common.repo_url.find(':')
                    prefix = common.repo_url[:i]
                    host = common.repo_url[(i + 3):]
                    file.write("withCredentials([[$class: 'UsernamePasswordMultiBinding', credentialsId: env.DMAKE_JENKINS_HTTP_CREDENTIALS, usernameVariable: 'GIT_USERNAME', passwordVariable: 'GIT_PASSWORD']]) {\n")
                    file.write('try {\n')
                    file.write("sh(\"git push --force '%s://${GIT_USERNAME}:${GIT_PASSWORD}@%s' refs/tags/%s\")\n" % (prefix, host, kwargs['tag']))
                    file.write("""} catch(error) {\nsh('echo "%s"')\n}\n""" % tag_push_error_msg.replace("'", "\\'"))
                    file.write("}\n")
                    file.write("""} catch(error) {\nsh('echo "Define \\'User/Password\\' credentials and set their ID in the \\'DMAKE_JENKINS_HTTP_CREDENTIALS\\' environment variable to be able to build and deploy only changed parts of the app."')\n}\n""")
                else:
                    file.write("sh('git push --force origin refs/tags/%s')\n" % kwargs['tag'])
                    file.write("""} catch(error) {\nsh('echo "%s"')\n}\n""" % tag_push_error_msg.replace("'", "\\'"))
        elif cmd == "junit":
            file.write("junit '%s'\n" % kwargs['report'])
        elif cmd == "cobertura":
            pass
        elif cmd == "publishHTML":
            file.write("publishHTML(target: [allowMissing: false, alwaysLinkToLastBuild: true, keepAll: false, reportDir: '%s', reportFiles: '%s', reportName: '%s'])\n" % (kwargs['directory'], kwargs['index'], kwargs['title'].replace("'", "\'")))
        elif cmd == "build":
            parameters = []
            for var, value in kwargs['parameters'].items():
                value = common.eval_str_in_env(value)
                parameters.append("string(name: '%s', value: '%s')" % (var.replace("'", "\\'"), value.replace("'", "\\'")))
            parameters = ','.join(parameters)
            file.write("build job: '%s', parameters: [%s], propagate: %s, wait: %s\n" % (
                    kwargs['job'].replace("'", "\\'"),
                    parameters,
                    "true" if kwargs['propagate'] else "false",
                    "true" if kwargs['wait'] else "false"))
        else:
            raise Exception("Unknown command %s" % cmd)

    file.write('}\n')
    file.write('finally {\n')
    file.write('sh("dmake_clean")\n')
    file.write('}\n')

###############################################################################

def generate_bash(file, cmds):
    file.write('set -e\n')
    for cmd, kwargs in cmds:
        if cmd == "stage":
            file.write("echo %s\n" % kwargs['name'])
        elif cmd == "sh":
            commands = kwargs['shell']
            if common.is_string(commands):
                commands = [commands]
            for c in commands:
                file.write("%s\n" % c)
        elif cmd == "read_sh":
            file.write("export %s=`%s`\n" % (kwargs['var'], kwargs['shell']))
            if kwargs['fail_if_empty']:
                file.write("if [ -z \"${%s}\" ]; then exit 1; fi\n" % kwargs['var'])
        elif cmd == "env":
            file.write('export %s="%s"\n' % (kwargs['var'], kwargs['value'].replace('"', '\\"')))
        elif cmd == "git_tag":
            file.write('git tag --force %s\n' % kwargs['tag'])
            file.write('git push --force origin refs/tags/%s || echo %s\n' % (kwargs['tag'], tag_push_error_msg))
        elif cmd == "junit":
            pass  # Should be configured with GUI
        elif cmd == "cobertura":
            pass  # Should be configured with GUI
        elif cmd == "publishHTML":
            pass  # Should be configured with GUI
        elif cmd == "build":
            pass  # Should be configured with GUI
        else:
            raise Exception("Unknown command %s" % cmd)

###############################################################################
