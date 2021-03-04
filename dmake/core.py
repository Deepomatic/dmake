import os
import subprocess
import sys
import uuid

import dmake.common as common
from dmake.common import DMakeException, SharedVolumeNotFoundException, append_command
from dmake.deepobuild import DMakeFile

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
    if common.change_detection_override_dirs is not None:
        changed_dirs = common.change_detection_override_dirs
        common.logger.info("Changed directories (forced via DMAKE_CHANGE_DETECTION_OVERRIDE_DIRS): %s", set(changed_dirs))
        return changed_dirs

    if not common.target:
        tag = get_tag_name()
        common.logger.info("Looking for changes between HEAD and %s" % tag)
        git_ref = "%s...HEAD" % tag

        try:
            common.run_shell_command2("git fetch origin +refs/tags/{tag}:refs/tags/{tag}".format(tag=tag))
        except common.ShellError as e:
            common.logger.debug("Fetching tag {} failed: {}".format(tag, e))
            common.logger.info("Tag {} not found on remote, assuming everything changed.")
            return None
    else:
        if common.is_local:
            common.logger.info("Looking for changes with {}".format(common.target))
            git_ref = common.target
        else:
            common.logger.info("Looking for changes between HEAD and %s" % common.target)
            git_ref = "%s/%s...HEAD" % (common.remote, common.target)

    try:
        output = common.run_shell_command("git diff --name-only %s" % git_ref)
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
    common.logger.debug("Changed files: %s", output)

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
    common.logger.info("Changed directories: %s", changed_dirs)
    return list(changed_dirs)

###############################################################################

def load_dmake_files_list():
    # Ignore permission issues when searching for dmake.yml files, in a portable way
    build_files = common.run_shell_command('dmake_find . -name dmake.yml').split("\n")
    build_files = filter(lambda f: len(f.strip()) > 0, build_files)
    build_files = [file[2:] for file in build_files]
    # Important: for block listed files: we load file in order from root to deepest file
    build_files = sorted(build_files, key = lambda path: len(os.path.dirname(path)))
    return build_files

###############################################################################

def add_service_provider(service_providers, service, file, needs = None, base_variant = None):
    """'service', 'needs' and 'base_variant' are all service names."""
    common.logger.debug("add_service_provider: service: %s, needs: %s, variant: %s" % (service, needs, base_variant))
    trigger_test_parents = set()
    if service in service_providers:
        existing_service_provider, _, _, trigger_test_parents = service_providers[service]
        # to construct parents links (when child trigger test on parents) (4th member of the tuple), we temporarily have service providers not defined yet, but already with some parents. It's materialized with file==None
        if existing_service_provider is not None:
            if existing_service_provider != file:
                raise DMakeException('Service %s re-defined in %s. First defined in %s' % (service, file, existing_service_provider))

    service_providers[service] = (file, needs, base_variant, trigger_test_parents)
    # add `service` to `trigger_test_parents` backlink for each needed_service child which was asked to trigger the parent test
    # `trigger_test_parents` == reverse link of `needs`, filtered on `needed_for.trigger_test`
    if needs is not None:
        for child_service, child_service_customization in needs:
            if not child_service_customization.needed_for.kind('trigger_test'):
                continue

            if child_service in service_providers:
                # TODO do we need to do something for child_service_customization?
                service_providers[child_service][3].add(service)
            else:
                service_providers[child_service] = (None, None, None, set([service]))

###############################################################################

def activate_file(loaded_files, service_providers, service_dependencies, command, file):
    dmake_file = loaded_files[file]
    if command in ['test', 'run', 'deploy', 'build_docker']:
        nodes = []
        for service in dmake_file.get_services():
            full_service_name = "%s/%s" % (dmake_file.app_name, service.service_name)
            nodes += activate_service(loaded_files, service_providers, service_dependencies, command, full_service_name)
        return nodes
    else:
        raise DMakeException('Unexpected command %s' % command)

###############################################################################

def activate_shared_volumes(shared_volumes):
    children = []
    for shared_volume in shared_volumes:
        shared_volume_service_name = shared_volume.get_service_name()
        children += [('shared_volume', shared_volume_service_name, None)]
    return children

###############################################################################

def activate_link_shared_volumes(loaded_files, service_providers, service):
    file, _, _, _ = service_providers[service]
    dmake = loaded_files[file]
    link = dmake.get_docker_link(service)

    try:
        shared_volumes = link.get_shared_volumes()
    except SharedVolumeNotFoundException as e:
        raise DMakeException("%s in docker_link '%s' in file '%s'" % (e, link.link_name, file))
    return activate_shared_volumes(shared_volumes)

###############################################################################

def activate_service_shared_volumes(loaded_files, service_providers, service):
    file, _, _, _ = service_providers[service]
    dmake = loaded_files[file]
    s = dmake._get_service_(service)

    try:
        shared_volumes = s.get_shared_volumes()
    except SharedVolumeNotFoundException as e:
        raise DMakeException("%s in service '%s' in file '%s'" % (e, s.service_name, file))
    return activate_shared_volumes(shared_volumes)

###############################################################################

def activate_base(base_variant):
    if base_variant is None:
        # base_variant is None when no base image is specified,
        # (only root_image is)
        # in which case we do not need to do anything
        return []
    return [('base', base_variant, None)]

###############################################################################

def activate_link(loaded_files, service_providers, service_dependencies, service):
    file, _, _, _ = service_providers[service]
    dmake = loaded_files[file]
    s = dmake._get_service_(service)

    children = []
    for link in s.needed_links:
        children += activate_service(loaded_files, service_providers, service_dependencies, 'run_link', 'links/%s/%s' % (dmake.get_app_name(), link))

    return children

###############################################################################

def activate_needed_services(loaded_files, service_providers, service_dependencies, needs, command, needed_for):
    children = []
    for service, service_customization in needs:
        if service_customization is None or service_customization.needed_for.kind(needed_for):
            children += activate_service(loaded_files, service_providers, service_dependencies, command, service, service_customization)
    return children

###############################################################################

def activate_service(loaded_files, service_providers, service_dependencies, command, service, service_customization=None):
    common.logger.debug("activate_service: command: %s,\tservice: %s,\tservice_customization: %s" % (command, service, service_customization))
    if command != 'run':
        assert service_customization == None
    node = (command, service, service_customization)
    if command == 'test' and common.skip_tests:
        return []

    if node not in service_dependencies:
        if service not in service_providers:
            raise DMakeException("Cannot find service: %s" % service)
        file, needs, base_variant, trigger_test_parents = service_providers[service]
        children = []
        if command == 'shell':
            children += activate_service_shared_volumes(loaded_files, service_providers, service)
            if common.options.with_dependencies and needs is not None:
                children += activate_needed_services(loaded_files, service_providers, service_dependencies, needs, command='run', needed_for='run')
            if common.options.with_dependencies:
                children += activate_link(loaded_files, service_providers, service_dependencies, service)
            children += activate_base(base_variant)
        elif command == 'test':
            children += activate_service_shared_volumes(loaded_files, service_providers, service)
            if common.options.with_dependencies and needs is not None:
                children += activate_needed_services(loaded_files, service_providers, service_dependencies, needs, command='run', needed_for='test')
            children += activate_service(loaded_files, service_providers, service_dependencies, 'build_docker', service)
            if common.options.with_dependencies:
                children += activate_link(loaded_files, service_providers, service_dependencies, service)
        elif command == 'build_docker':
            children += activate_base(base_variant)
        elif command == 'run':
            children += activate_service_shared_volumes(loaded_files, service_providers, service)
            # ~hackish: run service depends on test service if we are doing tests
            if common.command in ['test', 'deploy']:
                if common.change_detection:
                    # in change detection mode, don't add "test service" node: only create the link between run and test if the test node exists.
                    # the services to be tested are either:
                    # - created directly via graph construction starting on the target services: the ones that changed
                    # - independently created from "test child service" to "test parent service"
                    # we can reach here in the middle of the DAG construction (e.g. when multiple services have changed: we fully work one by one sequentially),
                    # so we don't know yet if the test node will exist at the end or not.
                    # the link will be created later, in a second global pass in make(), see "second pass" there
                    pass
                else:
                    # normal mode, activate "test service" as dependance of "run service"
                    # REMARK: if we wanted, we could change the semantic of `dmake test foo` to only test foo (while still running its dependencies needed for tests or run, recursively), instead of also testing all children services too: just use the second pass
                    children += activate_service(loaded_files, service_providers, service_dependencies, 'test', service)
            children += activate_service(loaded_files, service_providers, service_dependencies, 'build_docker', service)
            if common.options.with_dependencies and needs is not None:
                children += activate_needed_services(loaded_files, service_providers, service_dependencies, needs, command='run', needed_for='run')
            if common.options.with_dependencies:
                children += activate_link(loaded_files, service_providers, service_dependencies, service)
        elif command == 'run_link':
            children += activate_link_shared_volumes(loaded_files, service_providers, service)
        elif command == 'deploy':
            children += activate_service(loaded_files, service_providers, service_dependencies, 'build_docker', service)
            children += activate_service(loaded_files, service_providers, service_dependencies, 'test', service)
            if common.options.with_dependencies and needs is not None:
                # enforce deployment order by re-using needed_services dependency graph
                # but we don't want to create extra deployments because of customization
                # => deploy recursively using needs dependency, but ignore service customization
                uncustomized_needs = [(child_service, None) for child_service, child_service_customization in needs]
                children += activate_needed_services(loaded_files, service_providers, service_dependencies, uncustomized_needs, command='deploy', needed_for='fake__not_used')

        else:
            raise Exception("Unknown command '%s'" % command)

        service_dependencies[node] = children

        # parent dependencies, after updating service_dependencies to avoid infinite recursion
        # test parent when child changed
        if command == 'test':
            if common.options.with_dependencies and common.change_detection:
                for parent_service in trigger_test_parents:
                    common.logger.debug("activate_service: parent test: service: %s,\tparent service: %s" % (service, parent_service))
                    parent_node = activate_service(loaded_files, service_providers, service_dependencies, 'test', parent_service)[0]
                    if node not in service_dependencies[parent_node]:
                        service_dependencies[parent_node].append(node)

    return [node]

###############################################################################

def display_command_node(node):
    command, service, service_customization = node
    # daemon name: <app_name>/<service_name><optional_unique_suffix>; service already contains "<app_name>/"
    return "%s @ %s%s" % (command, service, service_customization.get_service_name_unique_suffix() if service_customization else "")

###############################################################################

def find_active_files(loaded_files, service_providers, service_dependencies, sub_dir, command):
    """Find file where changes have happened, and activate them; or activate all when common.force_full_deploy"""
    if common.force_full_deploy:
        common.logger.info("Forcing full re-build")
    else:
        # TODO warn if command == deploy: not really supported? or fatal error? or nothing?
        changed_dirs = look_for_changed_directories()

    def has_changed(root):
        for d in changed_dirs:
            if d.startswith(root):
                return True
        return False

    for file_name, dmake_file in loaded_files.items():
        if not file_name.startswith(sub_dir):
            continue
        root = os.path.dirname(file_name)
        if common.force_full_deploy or has_changed(root):
            activate_file(loaded_files, service_providers, service_dependencies, command, file_name)
            continue
        # still, maybe activate some services in this file with extended build context
        #  (to support docker_image.build.context: ../)
        for service in dmake_file.get_services():
            contexts = set()
            for additional_root in service.config.docker_image.get_source_directories_additional_contexts():
                contexts.add(os.path.normpath(os.path.join(root, additional_root)))
            # activate service if any of its additional contexts has changed
            for root in contexts:
                if has_changed(root):
                    full_service_name = "%s/%s" % (dmake_file.app_name, service.service_name)
                    activate_service(loaded_files, service_providers, service_dependencies, command, full_service_name)
                    break

###############################################################################

def load_dmake_file(loaded_files, blocklist, service_providers, service_dependencies, file):
    if file in loaded_files:
        return

    if file in blocklist:
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

    # Blocklist should be on child file because they are loaded this way

    # TODO: 'blacklist' is deprecated. Remove the two following lines when the
    # field will be completely removed
    for bl in dmake_file.blacklist:
        blocklist.append(bl)

    for bl in dmake_file.blocklist:
        blocklist.append(bl)

    for volume in dmake_file.volumes:
        shared_volume_service_name = volume.get_service_name()
        add_service_provider(service_providers, shared_volume_service_name, file)
        service_dependencies[('shared_volume', shared_volume_service_name, None)] = []

    for link in dmake_file.docker_links:
        add_service_provider(service_providers, 'links/%s/%s' % (dmake_file.get_app_name(), link.link_name), file)

    # Unroll docker image references
    if isinstance(dmake_file.docker, str):
        ref = dmake_file.docker
        load_dmake_file(loaded_files, blocklist, service_providers, service_dependencies, ref)
        if isinstance(loaded_files[ref].docker, str):
            raise DMakeException('Circular references: trying to load %s which is already loaded.' % loaded_files[ref].docker)
        dmake_file.__fields__['docker'] = loaded_files[ref].docker
    else:
        if isinstance(dmake_file.docker.root_image, str):
            ref = dmake_file.docker.root_image
            load_dmake_file(loaded_files, blocklist, service_providers, service_dependencies, ref)
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

    if isinstance(dmake_file.env, str):
        ref = dmake_file.env
        load_dmake_file(loaded_files, blocklist, service_providers, service_dependencies, ref)
        if isinstance(loaded_files[ref].env, str):
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
                raise DMakeException("Circular dependencies: %s" % ' -> '.join(map(str, reversed([dep] + walked_nodes))))
            depth = max(depth, 1 + sub_check(dep, walked_nodes))

        tree_depth[key] = depth
        return depth

    for k in dependencies:
        sub_check(k)

    leaves = []
    for k, v in is_leaf.items():
        if v:
            leaves.append((k, tree_depth[k]))

    return leaves, tree_depth

###############################################################################

def order_dependencies(dependencies, leaves):
    ordered_build_files = {}
    def sub_order(key, depth):
        if key in ordered_build_files and depth >= ordered_build_files[key]:
            return
        ordered_build_files[key] = depth
        if key in dependencies:
            for f in dependencies[key]:
                sub_order(f, depth - 1)

    for file, depth in leaves:
        sub_order(file, depth)
    return ordered_build_files

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

def generate_command_pipeline(file, cmds):
    indent_level = 0

    def write_line(data):
        if len(data) > 0:
            file.write('  ' * indent_level)
        file.write(data + '\n')

    if common.build_description is not None:
        write_line("currentBuild.description = '%s'" % common.build_description.replace("'", "\\'"))
    write_line("def dmake_echo(message) { sh(script: \"echo '${message}'\", label: message) }")
    write_line('try {')
    indent_level += 1

    cobertura_tests_results_dir = os.path.join(common.relative_cache_dir, 'cobertura_tests_results')
    emit_cobertura = False

    # checks to generate valid Jenkinsfiles
    check_no_duplicate_stage_names = set()
    check_no_duplicate_parallel_branch_names_stack = []

    for cmd, kwargs in cmds:
        if cmd == "stage":
            assert kwargs['name'] not in check_no_duplicate_stage_names, \
                'Duplicate stage name: {}'.format(kwargs['name'])
            check_no_duplicate_stage_names.add(kwargs['name'])

            name = kwargs['name'].replace("'", "\\'")
            write_line('')
            write_line("stage('%s') {" % name)
            indent_level += 1
        elif cmd == "stage_end":
            indent_level -= 1
            write_line("}")
        elif cmd == "parallel":
            # new scope on check_no_duplicate_parallel_branch_names stack
            check_no_duplicate_parallel_branch_names_stack.append(set())
            write_line("parallel(")
            indent_level += 1
        elif cmd == "parallel_end":
            indent_level -= 1
            write_line(")")
            # end scope on check_no_duplicate_parallel_branch_names stack
            check_no_duplicate_parallel_branch_names_stack.pop()
        elif cmd == "parallel_branch":
            assert kwargs['name'] not in check_no_duplicate_parallel_branch_names_stack[-1], \
                'Duplicate parallel_branch name: {}'.format(kwargs['name'])
            check_no_duplicate_parallel_branch_names_stack[-1].add(kwargs['name'])

            name = kwargs['name'].replace("'", "\\'")
            write_line("'%s': {" % name)
            indent_level += 1
        elif cmd == "parallel_branch_end":
            indent_level -= 1
            write_line("},")
        elif cmd == "lock":
            if 'quantity' not in kwargs:
                kwargs['quantity'] = 1
            if 'variable' not in kwargs:
                kwargs['variable'] = ""  # empty variable is accepted by the lock step as "'variable' not set"
            write_line("lock(label: '{label}', quantity: {quantity}, variable: '{variable}') {{".format(**kwargs))
            indent_level += 1
        elif cmd == "lock_end":
            indent_level -= 1
            write_line("}")
        elif cmd == "timeout":
            time = kwargs['time']
            write_line("timeout(time: %s, unit: 'SECONDS') {" % time)
            indent_level += 1
        elif cmd == "timeout_end":
            indent_level -= 1
            write_line("}")
        elif cmd == "try":
            write_line("try {")
            indent_level += 1
        elif cmd == "catch":
            what = kwargs['what']
            indent_level -= 1
            write_line("} catch(%s) {" % what)
            indent_level += 1
        elif cmd == "throw":
            what = kwargs['what']
            write_line("throw %s" % what)
        elif cmd == "catch_end":
            indent_level -= 1
            write_line("}")
        elif cmd == "echo":
            message = kwargs['message'].replace("'", "\\'")
            write_line("dmake_echo '%s'" % message)
        elif cmd == "sh":
            commands = kwargs['shell']
            if isinstance(commands, str):
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
            file_output = os.path.join(common.cache_dir, "output_%s" % uuid.uuid4())
            write_line("sh('%s > %s')" % (kwargs['shell'], file_output))
            write_line("env.%s = readFile '%s'" % (kwargs['var'], file_output))
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
                    write_line("sh('git push --force %s refs/tags/%s')" % (common.remote, kwargs['tag']))
                    error_msg = tag_push_error_msg
                indent_level -= 1
                write_line('} catch(error) {')
                write_line("""  sh('echo "%s"')""" % error_msg.replace("'", "\\'"))
                write_line('}')
        elif cmd == "junit":
            container_report = os.path.join(kwargs['mount_point'], kwargs['report'])
            host_report = os.path.join(common.relative_cache_dir, 'tests_results', str(uuid.uuid4()), kwargs['service_name'].replace(':', '-'), kwargs['report'])
            write_line('''sh('dmake_test_get_results "%s" "%s" "%s"')''' % (kwargs['service_name'], container_report, host_report))
            write_line("junit keepLongStdio: true, testResults: '%s'" % host_report)
            write_line('''sh('rm -rf "%s"')''' % host_report)
        elif cmd == "cobertura":
            container_report = os.path.join(kwargs['mount_point'], kwargs['report'])
            host_report = os.path.join(cobertura_tests_results_dir, str(uuid.uuid4()), kwargs['service_name'].replace(':', '-'), kwargs['report'])
            if not host_report.endswith('.xml'):
                raise DMakeException("`cobertura_report` must end with '.xml' in service '%s'" % kwargs['service_name'])
            write_line('''sh('dmake_test_get_results "%s" "%s" "%s"')''' % (kwargs['service_name'], container_report, host_report))
            # coberturaPublisher plugin only supports one step, so we delay generating it, and make it get all reports
            emit_cobertura = True
        elif cmd == "publishHTML":
            container_html_directory = os.path.join(kwargs['mount_point'], kwargs['directory'])
            host_html_directory = os.path.join(common.cache_dir, 'tests_results', str(uuid.uuid4()), kwargs['service_name'].replace(':', '-'), kwargs['directory'])
            write_line('''sh('dmake_test_get_results "%s" "%s" "%s"')''' % (kwargs['service_name'], container_html_directory, host_html_directory.rstrip('/')))
            write_line("publishHTML(target: [allowMissing: false, alwaysLinkToLastBuild: false, keepAll: true, reportDir: '%s', reportFiles: '%s', reportName: '%s'])" % (host_html_directory, kwargs['index'], kwargs['title'].replace("'", "\'")))
            write_line('''sh('rm -rf "%s"')''' % host_html_directory)
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
    indent_level += 1

    if emit_cobertura:
        write_line("step([$class: 'CoberturaPublisher', autoUpdateHealth: false, autoUpdateStability: false, coberturaReportFile: '%s/**/*.xml', failUnhealthy: false, failUnstable: false, maxNumberOfBuilds: 0, onlyStable: false, sourceEncoding: 'ASCII', zoomCoverageChart: false])" % (cobertura_tests_results_dir))
        write_line("publishCoverage adapters: [coberturaAdapter(mergeToOneReport: true, path: '%s/**/*.xml')], calculateDiffForChangeRequests: true, sourceFileResolver: sourceFiles('NEVER_STORE')" % (cobertura_tests_results_dir))
        write_line('''sh('rm -rf "%s"')''' % cobertura_tests_results_dir)

    write_line('sh("dmake_clean")')
    indent_level -= 1
    write_line('}')

###############################################################################

def generate_command_bash(file, cmds):
    assert not common.parallel_execution, "parallel execution not supported with bash runtime"

    indent_level = 0

    def write_line(data):
        if len(data) > 0:
            file.write('  ' * indent_level)
            file.write(data + '\n')

    write_line('test "${DMAKE_DEBUG}" = "1" && set -x')

    write_line("""
# from https://stackoverflow.com/a/25180186/15151442 for try/catch
function try()
{
    [[ $- = *e* ]]; SAVED_OPT_E=$?
    set +e
}

function throw()
{
    exit $1
}

function catch()
{
    export ex_code=$?
    (( $SAVED_OPT_E )) && set +e
    return $ex_code
}

function throwErrors()
{
    set -e
}

function ignoreErrors()
{
    set +e
}

""")

    write_line('set -e')
    for cmd, kwargs in cmds:
        if cmd == "stage":
            write_line("")
            write_line("{ echo -e '\n## %s ##'" % kwargs['name'])
            indent_level += 1
        elif cmd == "stage_end":
            indent_level -= 1
            write_line("}")
        elif cmd == "parallel":
            # parallel not supported with bash, fallback to running sequentially
            pass
        elif cmd == "parallel_end":
            pass
        elif cmd == "parallel_branch":
            # parallel_branch not supported with bash, fallback to running sequentially
            pass
        elif cmd == "parallel_branch_end":
            pass
        elif cmd == "lock":
            # lock not supported with bash, fallback to ignoring locks
            pass
        elif cmd == "lock_end":
            pass
        elif cmd == "timeout":
            # timeout not supported with bash, fallback to ignoring timeouts
            pass
        elif cmd == "timeout_end":
            pass
        elif cmd == "try":
            write_line("try")
            write_line("(")
            indent_level += 1
        elif cmd == "catch":
            what = kwargs['what']
            indent_level -= 1
            write_line(")")
            write_line("catch || { %s=$ex_code;" % what)
            indent_level += 1
        elif cmd == "throw":
            what = kwargs['what']
            write_line("throw $%s" % what)
        elif cmd == "catch_end":
            indent_level -= 1
            write_line("}")
        elif cmd == "echo":
            message = kwargs['message'].replace("'", "\\'")
            write_line("echo '%s'" % message)
        elif cmd == "sh":
            commands = kwargs['shell']
            if isinstance(commands, str):
                commands = [commands]
            for c in commands:
                write_line("%s" % c)
        elif cmd == "read_sh":
            write_line("%s=`%s`" % (kwargs['var'], kwargs['shell']))
            if kwargs['fail_if_empty']:
                write_line("if [ -z \"${%s}\" ]; then exit 1; fi" % kwargs['var'])
        elif cmd == "env":
            write_line('%s="%s"' % (kwargs['var'], kwargs['value'].replace('"', '\\"')))
            write_line('export %s' % kwargs['var'])
        elif cmd == "git_tag":
            write_line('git tag --force %s' % kwargs['tag'])
            write_line('git push --force %s refs/tags/%s || echo %s' % (common.remote, kwargs['tag'], tag_push_error_msg))
        elif cmd == "junit" or cmd == "cobertura":
            container_report = os.path.join(kwargs['mount_point'], kwargs['report'])
            host_report = make_path_unique_per_variant(kwargs['report'], kwargs['service_name'])
            write_line('dmake_test_get_results "%s" "%s" "%s"' % (kwargs['service_name'], container_report, host_report))
        elif cmd == "publishHTML":
            container_html_directory = os.path.join(kwargs['mount_point'], kwargs['directory'])
            host_html_directory = make_path_unique_per_variant(kwargs['directory'], kwargs['service_name'])
            write_line('dmake_test_get_results "%s" "%s" "%s"' % (kwargs['service_name'], container_html_directory, host_html_directory))
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

def service_completer(prefix, parsed_args, **kwargs):
    common.init(parsed_args, early_exit=True)
    files = make(parsed_args, parse_files_only=True)
    services = []
    for file, dmake_file in files.items():
        for service in dmake_file.get_services():
            services.append(service.service_name)
    return services

###############################################################################

def make(options, parse_files_only=False):
    app = getattr(options, 'service', None)

    if common.sub_dir:
        common.logger.info("Working in subdirectory: %s", common.sub_dir)

    # Format args
    auto_complete = False
    auto_completed_app = None
    if app == "*":
        # all services
        app = None
        common.force_full_deploy = True
    elif app == "+":
        # changed services only
        common.change_detection = True
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

    # Load all dmake.yml files (except those blocklisted)
    blocklist = []
    loaded_files = {}
    service_providers = {}
    service_dependencies = {}
    for file in build_files:
        load_dmake_file(loaded_files, blocklist, service_providers, service_dependencies, file)

    if parse_files_only:
        return loaded_files

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
                    if dmake_file.get_path().startswith(common.sub_dir):
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

    # Remove base images which are not provided (by dmake.yml definitions): they are external base images
    for deps in service_dependencies.values():
        to_delete = []
        for i, dep in enumerate(deps):
            if dep[1] not in service_providers:
                to_delete.append(i)
        to_delete.reverse()
        for i in to_delete:
            del deps[i]

    is_app_only = auto_completed_app is None or auto_completed_app.find('/') < 0

    if auto_completed_app is None:
        find_active_files(loaded_files, service_providers, service_dependencies, common.sub_dir, common.command)
    else:
        if is_app_only: # app only
            if common.command == 'shell':
                raise DMakeException("Could not find sub-app '%s'" % app)
            active_file = set()
            app_services = services[auto_completed_app]
            for service in app_services.values():
                full_service_name = "%s/%s" % (auto_completed_app, service.service_name)
                file, _, _, _ = service_providers[full_service_name]
                active_file.add(file)
            for file in active_file:
                activate_file(loaded_files, service_providers, service_dependencies, common.command, file)
        else:
            activate_service(loaded_files, service_providers, service_dependencies, common.command, auto_completed_app)

    # second pass
    for node in service_dependencies:
        command, service, service_customization = node
        if command == 'run' and common.change_detection:
            # guarantee "always test a service before running it" when change detection mode: run doesn't trigger test, but if test exists for other reasons, we still want to order it after run, see activate_service() command=='run' comments
            # remark: it's OK to assume the 3rd element of the test_node tuple is None: its the runtime service_customization: it's only set via needed_services for the command==run nodes only
            test_node = ('test', service, None)
            if test_node in service_dependencies:
                common.logger.debug('activate_service: second pass: change detection mode, adding link: run->test\tfor service: {}'.format(service))
                service_dependencies[node].append(test_node)
            else:
                common.logger.debug('activate_service: second pass: change detection mode, *not* adding link: run->test\tfor service: {}'.format(service))


    # (warning: tree vocabulary is reversed here: `leaves` are the nodes with no parent dependency, and depth is the number of levels of child dependencies)
    # check services circularity, and compute leaves, nodes_depth
    leaves, nodes_depth = check_no_circular_dependencies(service_dependencies)
    # get nodes leaves related to the dmake command (exclude notably `base` and `shared_volumes` which are created independently from the command)
    dmake_command_leaves = filter(lambda a_b__c: a_b__c[0][0] == common.command, leaves)
    # prepare reorder by computing shortest node depth starting from the dmake-command-created leaves
    #   WARNING: it seems to return different values than nodes_depth: seems to be min(child height)-1 here, vs max(parent height)+1 for nodes_depth (e.g. some run_links have >0 height, but no dependency)
    #   this effectively runs nodes as late as possible with build_files_order, and as soon as possible with nodes_depth
    build_files_order = order_dependencies(service_dependencies, dmake_command_leaves)

    # cleanup service_dependencies for debug dot graph: remove nodes with no depth: they are not related (directly or by dependency) to dmake-command-created leaves: they are not needed
    service_dependencies_pruned = dict(filter(lambda service_deps: service_deps[0] in build_files_order, service_dependencies.items()))

    debug_dot_graph = common.dump_debug_dot_graph(service_dependencies_pruned, nodes_depth)
    if common.exit_after_generate_dot_graph:
        print('Exiting after debug graph generation')
        return debug_dot_graph


    # Even with parallel execution we start with display (and thus compute) the execution plan the classic way: per stage and order.

    # Sort by order
    ordered_build_files = sorted(build_files_order.items(), key = lambda file_order: file_order[1])

    # Separate into base / build / tests / deploy
    if len(ordered_build_files) == 0:
        common.logger.info("Nothing to do:")
    else:
        n = len(ordered_build_files)
        base   = list(filter(lambda a_b__c: a_b__c[0][0] in ['base'], ordered_build_files))
        build  = list(filter(lambda a_b__c: a_b__c[0][0] in ['build_docker'], ordered_build_files))
        test   = list(filter(lambda a_b__c: a_b__c[0][0] in ['test', 'run_link', 'run', 'shared_volume'], ordered_build_files))
        deploy = list(filter(lambda a_b__c: a_b__c[0][0] in ['shell', 'deploy'], ordered_build_files))
        if len(base) + len(build) + len(test) + len(deploy) != len(ordered_build_files):
            raise Exception('Something went wrong when reorganizing build steps. One of the commands is probably missing.')

        ordered_build_files = [('Building Base', base),
                               ('Building App', build),
                               ('Running App', test)]

        if not common.is_pr:
            ordered_build_files.append(('Deploying', list(deploy)))

    common.logger.info("Here is the plan:")
    # Generate the list of command to run
    common.logger.info("Generating commands...")
    all_commands = []
    nodes_commands = {}
    nodes_need_gpu = {}

    init_commands = []
    append_command(init_commands, 'env', var = "REPO", value = common.repo)
    append_command(init_commands, 'env', var = "COMMIT", value = common.commit_id)
    append_command(init_commands, 'env', var = "BUILD", value = common.build_id)
    append_command(init_commands, 'env', var = "BRANCH", value = common.branch)
    append_command(init_commands, 'env', var = "NAME_PREFIX", value = common.name_prefix)
    append_command(init_commands, 'env', var = "DMAKE_TMP_DIR", value = common.tmp_dir)
    # check DMAKE_TMP_DIR still exists: detects unsupported jenkins reruns: clear error
    append_command(init_commands, 'sh', shell = 'dmake_check_tmp_dir')

    all_commands += init_commands
    for stage, commands in ordered_build_files:
        if len(commands) == 0:
            continue
        common.logger.info("## %s ##" % (stage))

        append_command(all_commands, 'stage', name = stage)

        stage_commands = []
        for node, order in commands:
            # Sanity check
            sub_task_orders = [build_files_order[a] for a in service_dependencies[node]]
            if any(map(lambda o: order <= o, sub_task_orders)):
                raise DMakeException('Bad ordering')

            command, service, service_customization = node
            file, _, _, _ = service_providers[service]
            dmake_file = loaded_files[file]
            app_name = dmake_file.get_app_name()
            links = docker_links[app_name]

            step_commands = []
            # temporarily reset need_gpu to isolate which step triggers it, for potential later parallel execution
            restore_need_gpu = common.need_gpu
            common.need_gpu = False
            try:
                if command == "base":
                    dmake_file.generate_base(step_commands, service)
                elif command == "shared_volume":
                    dmake_file.generate_shared_volume(step_commands, service)
                elif command == "shell":
                    dmake_file.generate_shell(step_commands, service, links, common.options.command)
                elif command == "test":
                    dmake_file.generate_test(step_commands, service, links)
                elif command == "run":
                    dmake_file.generate_run(step_commands, service, links, service_customization)
                elif command == "run_link":
                    dmake_file.generate_run_link(step_commands, service, links)
                elif command == "build_docker":
                    dmake_file.generate_build_docker(step_commands, service)
                elif command == "deploy":
                    dmake_file.generate_deploy(step_commands, service)
                else:
                    raise Exception("Unknown command '%s'" % command)
            except DMakeException as e:
                print(('ERROR in file %s:\n' % file) + str(e))
                sys.exit(1)

            nodes_commands[node] = step_commands
            nodes_need_gpu[node] = common.need_gpu
            common.need_gpu = restore_need_gpu

            if len(step_commands) > 0:
                node_display_str = display_command_node(node)
                common.logger.info("- {}".format(node_display_str))
                append_command(stage_commands, 'echo', message = '- Running {}'.format(node_display_str))
                stage_commands += step_commands

        # GPU resource lock
        # `common.need_gpu` is set during Testing commands generations: need to delay adding commands to all_commands to create the gpu lock if needed around the Testing stage
        lock_gpu = (stage == "Running App") and common.need_gpu
        if lock_gpu:
            append_command(all_commands, 'lock', label='GPUS', variable='DMAKE_GPU')

        all_commands += stage_commands

        if lock_gpu:
            append_command(all_commands, 'lock_end')

        append_command(all_commands, 'stage_end')


    # Parallel execution?
    if common.parallel_execution:
        common.logger.info("===============")
        common.logger.info("New plan: parallel execution, by height:")
        # Parallel execution: drop all_commands, start again (but reuse already computed nodes_commands)
        all_commands = []
        all_commands += init_commands

        # group nodes by height
        #   iterate on ordered_build_files instead of directly build_files_order to reuse common.is_pr filtering
        #   use nodes_depth instead of build_files_order/ordered_build_files order for ASAP execution instead of ALAP (As Late As Possible)
        nodes_by_height = {}
        deploy_nodes = []
        max_height = 0
        for stage, commands in ordered_build_files:
            for node, _ in commands:
                command = node[0]
                if command == 'deploy':
                    # isolate deploy to run them all in parallel at the end
                    deploy_nodes.append(node)
                    continue
                height = nodes_depth[node]
                max_height = max(max_height, height)
                if height not in nodes_by_height:
                    nodes_by_height[height] = []
                nodes_by_height[height].append(node)

        # inject back the deploy nodes as an extra height
        deploy_height = max_height + 1
        if deploy_nodes:
            nodes_by_height[deploy_height] = deploy_nodes

        # generate parallel by height
        gpu_locked = False
        for height, nodes in sorted(nodes_by_height.items()):
            common.logger.info("## height: %s ##" % (height))

            height_commands = []
            height_need_gpu = False
            for node in nodes:
                step_commands = nodes_commands[node]

                if len(step_commands) == 0:
                    continue

                height_need_gpu |= nodes_need_gpu[node]

                node_display_str = display_command_node(node)
                common.logger.info("- {}".format(node_display_str))

                append_command(height_commands, 'parallel_branch', name=node_display_str)
                if height != deploy_height:
                    # don't lock PARALLEL_BUILDERS on deploy height, it could lead to deployment deadlock if there is a deployment runtime dependancy between services
                    append_command(height_commands, 'lock', label='PARALLEL_BUILDERS')

                append_command(height_commands, 'echo', message = '- Running {}'.format(node_display_str))
                height_commands += step_commands

                if height != deploy_height:
                    # don't lock PARALLEL_BUILDERS on deploy height, it could lead to deployment deadlock if there is a deployment runtime dependancy between services
                    append_command(height_commands, 'lock_end')
                append_command(height_commands, 'parallel_branch_end')

            if len(height_commands) == 0:
                continue

            if height_need_gpu and not gpu_locked:
                append_command(all_commands, 'lock', label='GPUS', variable='DMAKE_GPU')
                gpu_locked = True

            append_command(all_commands, 'stage', name = "height {}".format(height))
            append_command(all_commands, 'parallel')

            all_commands += height_commands

            append_command(all_commands, 'parallel_end')
            append_command(all_commands, 'stage_end')

        if gpu_locked:
            append_command(all_commands, 'lock_end')

    # end parallel_execution



    # If not on Pull Request, tag the commit as deployed
    if common.command == "deploy" and not common.is_pr:
        append_command(all_commands, 'git_tag', tag = get_tag_name())

    # Generate output
    if common.is_local:
        file_to_generate = os.path.join(common.tmp_dir, "DMakefile")
    else:
        file_to_generate = "DMakefile"
    generate_command(file_to_generate, all_commands)
    common.logger.info("Commands have been written to %s" % file_to_generate)

    if common.command == "deploy" and common.is_local:
        r = input("Careful ! Are you sure you want to deploy ? [y/N]  ")
        if r.lower() != 'y':
            print('Aborting')
            sys.exit(0)

    # If on local, run the commands
    if common.is_local:
        common.logger.info("===============")
        common.logger.info("Executing plan...")
        result = subprocess.call('bash %s' % file_to_generate, shell=True)
        # Do not clean for the 'run' command
        do_clean = common.command not in ['build_docker', 'run']
        if result != 0 and common.command in ['shell', 'test']:
            r = input("An error was detected. DMake will stop. The script directory is : %s.\nDo you want to stop all the running containers? [Y/n]  " % common.tmp_dir)
            if r.lower() != 'y' and r != "":
                do_clean = False
        if do_clean:
            os.system('dmake_clean')
        sys.exit(result)
