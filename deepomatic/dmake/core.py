import os, sys

import deepomatic.dmake.common as common
from   deepomatic.dmake.common import DMakeException
from   deepomatic.dmake.deepobuild import DMakeFile, append_command


tag_push_error_msg = "Unauthorized to push the current state of deployment to git server. If the repository belongs to you, please check that the credentials declared in the DMAKE_JENKINS_SSH_AGENT_CREDENTIALS and DMAKE_JENKINS_HTTP_CREDENTIALS allow you to write to the repository."

###############################################################################

def find_symlinked_directories():
    symlinks = []
    for line in common.run_shell_command("for f in $(dmake_find . -type l); do echo \"$f $(ls -l $f | sed -e 's/.* -> //')\"; done").split('\n'):
        l = line.split(' ')
        if len(l) != 2:
            continue
        link_path = os.path.normpath(l[0])
        if not os.path.isdir(link_path):
            continue
        linked_dir = os.path.normpath(os.path.join(os.path.dirname(link_path), l[1]))
        if not os.path.isdir(linked_dir) or linked_dir[0] == '/':
            continue
        symlinks.append((link_path, linked_dir))
    return symlinks

def look_for_changed_directories():
    if common.force_full_deploy:
        return None
    if common.target is None:
        tag = get_tag_name()
        common.logger.info("Looking for changes between HEAD and %s" % tag)
        try:
            output = common.run_shell_command("git diff --name-only %s...HEAD" % tag)
        except common.ShellError as e:
            common.logger.error("Error: " + str(e))
            return None
    else:
        common.logger.info("Looking for changes between HEAD and %s" % common.target)
        try:
            output = common.run_shell_command("git diff --name-only origin/%s...HEAD" % common.target)
        except common.ShellError as e:
            common.logger.error("Error: " + str(e))
            return None

    if len(output) == 0:
        return []

    output = [file.strip() for file in output.split('\n')]
    symlinks = find_symlinked_directories()
    to_append = []
    for file in output:
        if len(file) == 0:
            continue
        for sl in symlinks:
            if file.startswith(sl[1]):
                f = file[len(sl[1]):]
                if len(f) == 0:
                    continue
                if f[0] == '/':
                    f = f[1:]
                to_append.append(os.path.join(sl[0], f))
    output += to_append

    #common.logger.info("Changed files:")
    #common.logger.info(output)

    changed_dirs = set()
    for file in output:
        if len(file) == 0:
            continue
        d = os.path.dirname(file)
        if d in changed_dirs:
            continue

        # Only keep bottom changed directories
        do_add = True
        to_remove = []
        for directory in changed_dirs:
            if directory.startswith(d): # sub directory of d
                do_add = False
            elif d.startswith(directory):
                to_remove = directory

        changed_dirs.difference_update(to_remove)
        if do_add:
            changed_dirs.add(d)
    return list(changed_dirs)

###############################################################################

def load_dmake_files_list():
    # Ignore permission issues when searching for dmake.yml files, in a portable way
    build_files = common.run_shell_command('dmake_find . -name dmake.yml').split("\n")
    build_files = filter(lambda f: len(f.strip()) > 0, build_files)
    build_files = [file[2:] for file in build_files]
    # Important: for black listed files: we load file in order from root to deepest file
    build_files = sorted(build_files, key = lambda path: len(os.path.dirname(path)))
    return build_files

###############################################################################

def add_service_provider(service_providers, service, file, needs = None, base_variant = None):
    """'service', 'needs' and 'base_variant' are all service names."""
    common.logger.debug("add_service_provider: service: %s, variant: %s" % (service, base_variant))
    if service in service_providers:
        existing_service_provider, _, _ = service_providers[service]
        if existing_service_provider != file:
            raise DMakeException('Service %s re-defined in %s. First defined in %s' % (service, file, existing_service_provider))
    else:
        service_providers[service] = (file, needs, base_variant)

###############################################################################

def activate_file(loaded_files, service_providers, service_dependencies, command, file):
    dmake_file = loaded_files[file]
    if command in ['test', 'run', 'deploy']:
        nodes = []
        for service in dmake_file.get_services():
            full_service_name = "%s/%s" % (dmake_file.app_name, service.service_name)
            nodes += activate_service(loaded_files, service_providers, service_dependencies, command, full_service_name)
        return nodes
    else:
        raise DMakeException('Unexpected command %s' % command)

###############################################################################

def activate_base(base_variant):
    return [('base', base_variant, None)]

###############################################################################

def activate_link(loaded_files, service_providers, service_dependencies, service):
    file, _, _ = service_providers[service]
    dmake = loaded_files[file]
    s = dmake._get_service_(service)

    children = []
    for link in s.needed_links:
        children += activate_service(loaded_files, service_providers, service_dependencies, 'run_link', 'links/%s/%s' % (dmake.get_app_name(), link))

    return children

###############################################################################

def activate_needed_services(loaded_files, service_providers, service_dependencies, needs):
    children = []
    for service, service_customization in needs:
        children += activate_service(loaded_files, service_providers, service_dependencies, 'run', service, service_customization)
    return children

###############################################################################

def activate_service(loaded_files, service_providers, service_dependencies, command, service, service_customization=None):
    node = (command, service, service_customization)
    if command == 'test' and common.skip_tests:
        return []

    with_dependencies = getattr(common.options, 'dependencies', None)

    if node not in service_dependencies:
        if service not in service_providers:
            raise DMakeException("Cannot find service: %s" % service)
        file, needs, base_variant = service_providers[service]
        if command == 'shell':
            children = []
            if with_dependencies and needs is not None:
                children += activate_needed_services(loaded_files, service_providers, service_dependencies, needs)
                children += activate_link(loaded_files, service_providers, service_dependencies, service)
            children += activate_base(base_variant)
        elif command == 'test':
            children = []
            if with_dependencies and needs is not None:
                children += activate_needed_services(loaded_files, service_providers, service_dependencies, needs)
            children += activate_service(loaded_files, service_providers, service_dependencies, 'build', service)
            if with_dependencies:
                children += activate_link(loaded_files, service_providers, service_dependencies, service)
        elif command == 'build':
            children = activate_base(base_variant)
        elif command == 'build_docker':
            children = activate_base(base_variant)
        elif command == 'run':
            children = activate_service(loaded_files, service_providers, service_dependencies, 'build_docker', service)
            if with_dependencies and needs is not None:
                children += activate_needed_services(loaded_files, service_providers, service_dependencies, needs)
                children += activate_link(loaded_files, service_providers, service_dependencies, service)
        elif command == 'run_link':
            children = []
        elif command == 'deploy':
            children  = activate_service(loaded_files, service_providers, service_dependencies, 'test', service)
            children += activate_service(loaded_files, service_providers, service_dependencies, 'build_docker', service)
        else:
            raise Exception("Unknown command '%s'" % command)

        service_dependencies[node] = children

    return [node]

###############################################################################

def display_command_node(node):
    command, service, service_customization = node
    # daemon name: <app_name>/<service_name><optional_unique_suffix>; service already contains "<app_name>/"
    return "%s @ %s%s" % (command, service, service_customization.get_service_name_unique_suffix() if service_customization else "")

###############################################################################

def find_active_files(loaded_files, service_providers, service_dependencies, sub_dir, command):
    changed_dirs = look_for_changed_directories()
    if changed_dirs is None:
        common.logger.info("Forcing full re-build")

    for file_name, dmake in loaded_files.items():
        if not file_name.startswith(sub_dir):
            continue
        root = os.path.dirname(file_name)
        active = False
        if changed_dirs is None:
            active = True
        else:
            for d in changed_dirs:
                if d.startswith(root):
                    active = True

        if active:
            activate_file(loaded_files, service_providers, service_dependencies, command, file_name)

###############################################################################

def load_dmake_file(loaded_files, blacklist, service_providers, service_dependencies, file):
    if file in loaded_files:
        return

    if file in blacklist:
        return

    # Load YAML and check version
    with open(file, 'r') as stream:
        data = common.yaml_ordered_load(stream)
    if 'dmake_version' not in data:
        raise DMakeException("Missing field 'dmake_version' in %s" % file)
    version = str(data['dmake_version'])
    if version not in ['0.1']:
        raise DMakeException("Incorrect version '%s'" % str(data['dmake_version']))

    # Load appropriate version (TODO: versionning)
    if version == '0.1':
        dmake_file = DMakeFile(file, data)
    loaded_files[file] = dmake_file

    # Blacklist should be on child file because they are loaded this way
    for bl in dmake_file.blacklist:
        blacklist.append(bl)

    for link in dmake_file.docker_links:
        add_service_provider(service_providers, 'links/%s/%s' % (dmake_file.get_app_name(), link.link_name), file)

    # Unroll docker image references
    if common.is_string(dmake_file.docker):
        ref = dmake_file.docker
        load_dmake_file(loaded_files, blacklist, service_providers, service_dependencies, ref)
        if common.is_string(loaded_files[ref].docker):
            raise DMakeException('Circular references: trying to load %s which is already loaded.' % loaded_files[ref].docker)
        dmake_file.__fields__['docker'] = loaded_files[ref].docker
    else:
        if common.is_string(dmake_file.docker.root_image):
            ref = dmake_file.docker.root_image
            load_dmake_file(loaded_files, blacklist, service_providers, service_dependencies, ref)
            dmake_file.docker.__fields__['root_image'] = loaded_files[ref].docker.root_image
        elif dmake_file.docker.root_image is not None:
            default_root_image = dmake_file.docker.root_image
            default_root_image = common.eval_str_in_env(default_root_image.name + ":" + default_root_image.tag)
            dmake_file.docker.__fields__['root_image'] = default_root_image

        default_root_image = dmake_file.docker.root_image
        for base_image in dmake_file.docker.base_image:
            base_image_service = base_image.get_service_name()
            base_image_name = base_image.get_name_variant()
            root_image = base_image.root_image
            if root_image is None:
                # set default root_image
                if default_root_image is None:
                    raise DMakeException("Missing field 'root_image' (and default 'docker.root_image') for base_image '%s' in '%s'" % (base_image_name, file))
                root_image = default_root_image
                base_image.__fields__['root_image'] = root_image

            add_service_provider(service_providers, base_image_service, file)
            service_dependencies[('base', base_image_service, None)] = [('base', root_image, None)]
        if len(dmake_file.docker.base_image) == 0 and default_root_image is None:
            raise DMakeException("Missing field 'docker.root_image' in '%s'" % (file))

    if common.is_string(dmake_file.env):
        ref = dmake_file.env
        load_dmake_file(loaded_files, blacklist, service_providers, service_dependencies, ref)
        if common.is_string(loaded_files[ref].env):
            raise DMakeException('Circular references: trying to load %s which is already loaded.' % ref)
        dmake_file.__fields__['env'] = loaded_files[ref].env

###############################################################################

def check_no_circular_dependencies(dependencies):
    is_leaf = {}
    for k in dependencies:
        is_leaf[k] = True

    tree_depth = {}
    def sub_check(key, walked_nodes = []):
        if key in tree_depth:
            return tree_depth[key]
        if key not in dependencies:
            return 0

        walked_nodes = [key] + walked_nodes
        depth = 0
        for dep in dependencies[key]:
            is_leaf[dep] = False
            if dep in walked_nodes:
                raise DMakeException("Circular dependencies: %s" % ' -> '.join(reversed([dep] + walked_nodes)))
            depth = max(depth, 1 + sub_check(dep, walked_nodes))

        tree_depth[key] = depth
        return depth

    for k in dependencies:
        sub_check(k)

    leaves = []
    for k, v in is_leaf.items():
        if v:
            leaves.append((k, tree_depth[k]))

    sorted(leaves, key = lambda k_depth: k_depth[1], reverse = True)
    return leaves

###############################################################################

def order_dependencies(dependencies, sorted_leaves):
    ordered_build_files = {}
    def sub_order(key, depth):
        if key in ordered_build_files and depth >= ordered_build_files[key]:
            return
        ordered_build_files[key] = depth
        if key in dependencies:
            for f in dependencies[key]:
                sub_order(f, depth - 1)

    for file, depth in sorted_leaves:
        sub_order(file, depth)
    return ordered_build_files

###############################################################################

def generate_command_pipeline(file, cmds):
    indent_level = 0

    def write_line(data):
        if len(data) > 0:
            file.write('  ' * indent_level)
        file.write(data + '\n')

    if common.build_description is not None:
        write_line("currentBuild.description = '%s'" % common.build_description.replace("'", "\\'"))
    write_line('try {')
    indent_level += 1

    for cmd, kwargs in cmds:
        if cmd == "stage":
            name = kwargs['name'].replace("'", "\\'")
            write_line('')
            if kwargs['concurrency'] is not None and kwargs['concurrency'] > 1:
                raise DMakeException("Unsupported stage concurrency: %s > 1" % kwargs['concurrency'])
            write_line("stage('%s') {" % name)
            indent_level += 1
        elif cmd == "stage_end":
            indent_level -= 1
            write_line("}")
        elif cmd == "echo":
            message = kwargs['message'].replace("'", "\\'")
            write_line("echo '%s'" % message)
        elif cmd == "sh":
            commands = kwargs['shell']
            if common.is_string(commands):
                commands = [commands]
            commands = [common.escape_cmd(c) for c in commands]
            if len(commands) == 0:
                return
            if len(commands) == 1:
                write_line('sh("%s")' % commands[0])
            else:
                write_line('parallel (')
                commands_list = []
                for c in enumerate(commands):
                    commands_list.append("cmd%d: { sh('%s') }" % c)
                write_line(','.join(commands_list))
                write_line(')')
        elif cmd == "read_sh":
            file_output = os.path.join(common.root_dir, ".dmake", "output_%d" % kwargs['id'])
            write_line("sh('%s > %s')" % (kwargs['shell'], file_output))
            write_line("env.%s = readFile '%s'" % (kwargs['var'], file_output));
            if kwargs['fail_if_empty']:
                write_line("sh('if [ -z \"${%s}\" ]; then exit 1; fi')" % kwargs['var'])
        elif cmd == "env":
            write_line('env.%s = "%s"' % (kwargs['var'], kwargs['value']))
        elif cmd == "git_tag":
            if common.repo_url is not None:
                write_line("sh('git tag --force %s')" % kwargs['tag'])
                write_line('try {')
                indent_level += 1
                if common.repo_url.startswith('https://') or common.repo_url.startswith('http://'):
                    i = common.repo_url.find(':')
                    prefix = common.repo_url[:i]
                    host = common.repo_url[(i + 3):]
                    write_line("withCredentials([[$class: 'UsernamePasswordMultiBinding', credentialsId: env.DMAKE_JENKINS_HTTP_CREDENTIALS, usernameVariable: 'GIT_USERNAME', passwordVariable: 'GIT_PASSWORD']]) {")
                    indent_level += 1
                    write_line('try {')
                    write_line("""  sh("git push --force '%s://${GIT_USERNAME}:${GIT_PASSWORD}@%s' refs/tags/%s")""" % (prefix, host, kwargs['tag']))
                    write_line('} catch(error) {')
                    write_line("""  sh('echo "%s"')""" % tag_push_error_msg.replace("'", "\\'"))
                    write_line('}')
                    error_msg = "Define 'User/Password' credentials and set their ID in the 'DMAKE_JENKINS_HTTP_CREDENTIALS' environment variable to be able to build and deploy only changed parts of the app."
                    indent_level -= 1
                    write_line('}')
                else:
                    write_line("sh('git push --force origin refs/tags/%s')" % kwargs['tag'])
                    error_msg = tag_push_error_msg
                indent_level -= 1
                write_line('} catch(error) {')
                write_line("""  sh('echo "%s"')""" % error_msg.replace("'", "\\'"))
                write_line('}')
        elif cmd == "junit":
            write_line("junit '%s'" % kwargs['report'])
        elif cmd == "cobertura":
            write_line("step([$class: 'CoberturaPublisher', autoUpdateHealth: false, autoUpdateStability: false, coberturaReportFile: '%s', failUnhealthy: false, failUnstable: false, maxNumberOfBuilds: 0, onlyStable: false, sourceEncoding: 'ASCII', zoomCoverageChart: false])" % (kwargs['report']))
        elif cmd == "publishHTML":
            write_line("publishHTML(target: [allowMissing: false, alwaysLinkToLastBuild: true, keepAll: false, reportDir: '%s', reportFiles: '%s', reportName: '%s'])" % (kwargs['directory'], kwargs['index'], kwargs['title'].replace("'", "\'")))
        elif cmd == "build":
            parameters = []
            for var, value in kwargs['parameters'].items():
                value = common.eval_str_in_env(value)
                parameters.append("string(name: '%s', value: '%s')" % (var.replace("'", "\\'"), value.replace("'", "\\'")))
            parameters = ','.join(parameters)
            write_line("build job: '%s', parameters: [%s], propagate: %s, wait: %s" % (
                    kwargs['job'].replace("'", "\\'"),
                    parameters,
                    "true" if kwargs['propagate'] else "false",
                    "true" if kwargs['wait'] else "false"))
        else:
            raise DMakeException("Unknown command %s" % cmd)

    indent_level -= 1
    write_line('}')
    write_line('catch (error) {')
    write_line('  if ( env.DMAKE_PAUSE_ON_ERROR_BEFORE_CLEANUP == "1" ) {')
    write_line('    slackSend channel: "#jenkins-dmake", message: "This jenkins build requires your attention: <${env.BUILD_URL}/console|${env.JOB_NAME} ${env.BUILD_NUMBER}>"')
    write_line("    input message: 'An error occurred. DMake will stop and clean all the running containers upon any answer.'")
    write_line('  }')
    write_line('  throw error')
    write_line('}')
    write_line('finally {')
    write_line('  sh("dmake_clean")')
    write_line('}')

###############################################################################

def generate_command_bash(file, cmds):
    file.write('test "${DMAKE_DEBUG}" = "1" && set -x\n')
    file.write('set -e\n')
    for cmd, kwargs in cmds:
        if cmd == "stage":
            file.write("\n")
            file.write("echo -e '\n## %s ##'\n" % kwargs['name'])
        elif cmd == "stage_end":
            pass
        elif cmd == "echo":
            message = kwargs['message'].replace("'", "\\'")
            file.write("echo '%s'\n" % message)
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
            raise DMakeException("Unknown command %s" % cmd)

###############################################################################

def generate_command(file_name, cmds):
    with open(file_name, "w") as file:
        if common.use_pipeline:
            generate_command_pipeline(file, cmds)
        else:
            generate_command_bash(file, cmds)

###############################################################################

def get_tag_name():
    return 'deployed_version_%s' % common.branch

###############################################################################

def make(root_dir, sub_dir, command, app, options):
    if 'DMAKE_TMP_DIR' in os.environ:
        del os.environ['DMAKE_TMP_DIR']
    common.init(command, root_dir, app, options)

    if app == "":
        app = None

    if common.command == "stop":
        common.run_shell_command("docker rm -f `docker ps -q -f name=%s.%s.%s`" % (common.repo, common.branch, common.build_id))
        return

    # Format args
    auto_complete = False
    auto_completed_app = None
    if app == "*":
        app = None
        common.force_full_deploy = True
    elif app is not None:
        n = len(app.split('/'))
        if n > 2:
            raise DMakeException('Cannot have more than one slash in the app name')
        auto_complete = n == 1
        if not auto_complete:
            auto_completed_app = app
        common.force_full_deploy = True
    elif common.command in ['shell']:
        auto_complete = True

    # Load build files
    build_files = load_dmake_files_list()
    if len(build_files) == 0:
        raise DMakeException('No dmake.yml file found !')

    # Load all dmake.yml files (except those blacklisted)
    blacklist = []
    loaded_files = {}
    service_providers = {}
    service_dependencies = {}
    for file in build_files:
        load_dmake_file(loaded_files, blacklist, service_providers, service_dependencies, file)

    # Register all apps and services in the repo
    docker_links = {}
    services = {}
    for file, dmake_file in loaded_files.items():
        if dmake_file.env is not None and dmake_file.env.source is not None:
            try:
                common.pull_config_dir(os.path.dirname(dmake_file.env.source))
            except common.NotGitRepositoryException:
                common.logger.warning('Not a Git repository: %s' % (dmake_file.env.source))

        app_name = dmake_file.get_app_name()
        if app_name not in docker_links:
            docker_links[app_name] = {}
        if app_name not in services:
            services[app_name] = {}

        app_services = services[app_name]
        for service in dmake_file.get_services():
            full_service_name = "%s/%s" % (app_name, service.service_name)
            if service.service_name in app_services:
                raise DMakeException("Duplicated sub-app name: '%s'" % full_service_name)

            needs = [("%s/%s" % (app_name, sa.service_name), sa) for sa in service.needed_services]

            base_variant = None
            try:
                base_image = dmake_file.docker.get_base_image(variant=service.get_base_image_variant())
            except DMakeException as e:
                raise DMakeException("%s, for service '%s' in file '%s'" % (e, full_service_name, file))
            if base_image is not None:
                base_variant = base_image.get_service_name()

            add_service_provider(service_providers, full_service_name, file, needs, base_variant)
            app_services[service.service_name] = service

            if auto_complete:
                if app is None:
                    if dmake_file.get_path().startswith(sub_dir):
                        if auto_completed_app is None:
                            auto_completed_app = full_service_name
                            break # A bit hacky: we actually do not care about the full service name: we just want to select the proper dmake file.
                        else:
                            raise DMakeException("Ambigous service name: both services '%s' and '%s' are matching the current path." % (full_service_name, auto_completed_app))
                else:
                    if service.service_name == app:
                        if auto_completed_app is None:
                            auto_completed_app = full_service_name
                        else:
                            raise DMakeException("Ambigous service name '%s' is matching '%s' and '%s'" % (app, full_service_name, auto_completed_app))

        app_links = docker_links[app_name]
        for link in dmake_file.get_docker_links():
            if link.link_name in app_links:
                raise DMakeException("Duplicate link name '%s' for application '%s'. Link names must be unique inside each app." % (link.link_name, app_name))
            app_links[link.link_name] = link

    if auto_complete and auto_completed_app is None:
        raise DMakeException("Could not find any app or sub-app matching '%s'" % app)

    # Filter base images which are not provided
    for deps in service_dependencies.values():
        to_delete = []
        for i, dep in enumerate(deps):
            if dep[1] not in service_providers:
                to_delete.append(i)
        to_delete.reverse()
        for i in to_delete:
            del deps[i]

    is_app_only = auto_completed_app is None or auto_completed_app.find('/') < 0
    if common.command == "run" and is_app_only:
        common.options.dependencies = True

    if auto_completed_app is None:
        # Find file where changes have happened
        find_active_files(loaded_files, service_providers, service_dependencies, sub_dir, common.command)
    else:
        if is_app_only: # app only
            if common.command == 'shell':
                raise DMakeException("Could not find sub-app '%s'" % app)
            active_file = set()
            app_services = services[auto_completed_app]
            for service in app_services.values():
                full_service_name = "%s/%s" % (auto_completed_app, service.service_name)
                file, _, _ = service_providers[full_service_name]
                active_file.add(file)
            for file in active_file:
                activate_file(loaded_files, service_providers, service_dependencies, common.command, file)
        else:
            activate_service(loaded_files, service_providers, service_dependencies, common.command, auto_completed_app)

    # check services circularity
    sorted_leaves = check_no_circular_dependencies(service_dependencies)
    sorted_leaves = filter(lambda a_b__c: a_b__c[0][0] == common.command, sorted_leaves)
    build_files_order = order_dependencies(service_dependencies, sorted_leaves)

    # Sort by order
    ordered_build_files = sorted(build_files_order.items(), key = lambda file_order: file_order[1])

    # Separate into base / build / tests / deploy
    if len(ordered_build_files) == 0:
        common.logger.info("Nothing to do:")
    else:
        n = len(ordered_build_files)
        base   = list(filter(lambda a_b__c: a_b__c[0][0] in ['base'], ordered_build_files))
        build  = list(filter(lambda a_b__c: a_b__c[0][0] in ['build', 'build_docker'], ordered_build_files))
        test   = list(filter(lambda a_b__c: a_b__c[0][0] in ['test', 'run_link', 'run'], ordered_build_files))
        deploy = list(filter(lambda a_b__c: a_b__c[0][0] in ['shell', 'deploy'], ordered_build_files))
        if len(base) + len(build) + len(test) + len(deploy) != len(ordered_build_files):
            raise Exception('Something went wrong when reorganizing build steps. One of the commands is probably missing.')

        ordered_build_files = [('Building Base', base),
                               ('Building App', build),
                               ('Testing App', test)]

        if not common.is_pr:
            ordered_build_files.append(('Deploying', list(deploy)))

        # Display commands
        common.logger.info("Here is the plan:")
        for stage, commands in ordered_build_files:
            if len(commands) > 0:
                common.logger.info("## %s ##" % (stage))
            for node, order in commands:
                # Sanity check
                sub_task_orders = [build_files_order[a] for a in service_dependencies[node]]
                if any(map(lambda o: order <= o, sub_task_orders)):
                    raise DMakeException('Bad ordering')

                common.logger.info("- %s" % (display_command_node(node)))

    # Generate the list of command to run
    common.logger.info("Generating commands...")
    all_commands = []
    append_command(all_commands, 'env', var = "REPO", value = common.repo)
    append_command(all_commands, 'env', var = "COMMIT", value = common.commit_id)
    append_command(all_commands, 'env', var = "BUILD", value = common.build_id)
    append_command(all_commands, 'env', var = "BRANCH", value = common.branch)
    append_command(all_commands, 'env', var = "DMAKE_TMP_DIR", value = common.tmp_dir)

    for stage, commands in ordered_build_files:
        if len(commands) == 0:
            continue

        append_command(all_commands, 'stage', name = stage, concurrency = 1 if stage == "Deploying" else None)
        for node, order in commands:
            command, service, service_customization = node
            file, _, _ = service_providers[service]
            dmake_file = loaded_files[file]
            app_name = dmake_file.get_app_name()
            links = docker_links[app_name]

            step_commands = []
            try:
                if command == "base":
                    dmake_file.generate_base(step_commands, service)
                elif command == "shell":
                    dmake_file.generate_shell(step_commands, service, links)
                elif command == "test":
                    dmake_file.generate_test(step_commands, service, links)
                elif command == "run":
                    dmake_file.generate_run(step_commands, service, links, service_customization)
                elif command == "run_link":
                    dmake_file.generate_run_link(step_commands, service, links)
                elif command == "build":
                    dmake_file.generate_build(step_commands, service)
                elif command == "build_docker":
                    dmake_file.generate_build_docker(step_commands, service)
                elif command == "deploy":
                    dmake_file.generate_deploy(step_commands, service)
                else:
                    raise Exception("Unknown command '%s'" % command)
            except DMakeException as e:
                print(('ERROR in file %s:\n' % file) + str(e))
                sys.exit(1)

            if len(step_commands) > 0:
                append_command(all_commands, 'echo', message = '- Running %s' % (display_command_node(node)))
                all_commands += step_commands

        append_command(all_commands, 'stage_end')


    # Check stages do not appear twice (otherwise it may block Jenkins)
    stage_names = set()
    for cmd, kwargs in all_commands:
        if cmd == "stage":
            name = kwargs['name']
            if name in stage_names:
                raise DMakeException('Duplicate stage name: %s' % name)
            else:
                stage_names.add(name)

    # If not on Pull Request, tag the commit as deployed
    if common.command == "deploy" and not common.is_pr:
        append_command(all_commands, 'git_tag', tag = get_tag_name())

    # Generate output
    if common.is_local:
        file_to_generate = os.path.join(common.tmp_dir, "DMakefile")
    else:
        file_to_generate = "DMakefile"
    generate_command(file_to_generate, all_commands)
    common.logger.info("Output has been written to %s" % file_to_generate)

    if common.command == "deploy" and common.is_local:
        r = common.read_input("Careful ! Are you sure you want to deploy ? [Y/n] ")
        if r.lower() != 'y' and r != "":
            print('Aborting')
            sys.exit(0)

    # If on local, run the commands
    if common.is_local:
        result = os.system('bash %s' % file_to_generate)
        # Do not clean for the 'run' command
        do_clean = common.command != 'run'
        if result != 0 and common.command in ['shell', 'test']:
            r = common.read_input("An error was detected. DMake will stop. The script directory is : %s.\nDo you want to stop all the running containers? [Y/n] " % common.tmp_dir)
            if r.lower() != 'y' and r != "":
                do_clean = False
        if do_clean:
            os.system('dmake_clean')
