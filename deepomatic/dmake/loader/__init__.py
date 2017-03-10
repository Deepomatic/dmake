import os
import yaml
import deepomatic.dmake.common as common
from   deepomatic.dmake.common import DMakeException
import deepomatic.dmake.loader.v0_1 as v0_1

###############################################################################

def add_service_provider(service_providers, service, file, needs = None):
    if service in service_providers:
        if service_providers[service] != file:
            raise DMakeException('Service %s re-defined in %s. First defined in %s' % (service, file, service_providers[service]))
    else:
        service_providers[service] = (file, needs)

###############################################################################

def activate_file(loaded_files, service_providers, service_dependencies, command, file):
    file_deps = {
        'build': 'base',
    }

    dmake_file = loaded_files[file]
    if command == 'base':
        root_image = dmake_file.docker.root_image
        base_image = dmake_file.docker.get_docker_base_image_name_tag()
        if root_image != base_image:
            return [('base', base_image)]
        else:
            return []
    elif command in file_deps:
        node = (command, file)
        if node not in service_dependencies:
            service_dependencies[node] = activate_file(loaded_files, service_providers, service_dependencies, file_deps[command], file)
        return [node]
    elif command in ['test', 'run', 'deploy']:
        nodes = []
        for service in dmake_file.get_services():
            full_service_name = "%s/%s" % (dmake_file.app_name, service.service_name)
            nodes += activate_service(loaded_files, service_providers, service_dependencies, command, full_service_name)
        return nodes
    else:
        raise DMakeException('Unexpected command %s' % command)

###############################################################################

def activate_link(loaded_files, service_providers, service_dependencies, service):
    file, _ = service_providers[service]
    dmake = loaded_files[file]
    s = dmake._get_service_(service)

    children = []
    if s.tests.has_value():
        for link in s.tests.docker_links_names:
            children += activate_service(loaded_files, service_providers, service_dependencies, 'run_link', 'links/%s/%s' % (dmake.get_app_name(), link))

    return children

###############################################################################

def activate_service(loaded_files, service_providers, service_dependencies, command, service):
    node = (command, service)
    if command == 'test' and common.skip_tests:
        return []

    if node not in service_dependencies:
        file, needs = service_providers[service]

        # Build base docker image of a dmake file
        if command == 'base':
            children = activate_file(loaded_files, service_providers, service_dependencies, 'base', file)

        # Launch a shell on a service
        elif command == 'shell':
            children = []
            if getattr(common.options, 'dependencies', None) and needs is not None:
                for n in needs:
                    children += activate_service(loaded_files, service_providers, service_dependencies, 'run', n)
                children += activate_link(loaded_files, service_providers, service_dependencies, service)
            children += activate_file(loaded_files, service_providers, service_dependencies, 'base', file)

        # Test a service
        elif command == 'test':
            children = []
            if getattr(common.options, 'dependencies', None) and needs is not None:
                for n in needs:
                    children += activate_service(loaded_files, service_providers, service_dependencies, 'run', n)
            children += activate_file(loaded_files, service_providers, service_dependencies, 'build', file)
            if getattr(common.options, 'dependencies', None):
                children += activate_link(loaded_files, service_providers, service_dependencies, service)

        # Build the deployment ready docker image
        elif command == 'build_docker':
            children = activate_file(loaded_files, service_providers, service_dependencies, 'base', file)

        # Launch a service
        elif command == 'run':
            children = activate_service(loaded_files, service_providers, service_dependencies, 'build_docker', service)
            if getattr(common.options, 'dependencies', None) and needs is not None:
                for n in needs:
                    children += activate_service(loaded_files, service_providers, service_dependencies, 'run', n)
                children += activate_link(loaded_files, service_providers, service_dependencies, service)

        # Launch a third party service
        elif command == 'run_link':
            children = []

        # Deploy a service
        elif command == 'deploy':
            children  = activate_service(loaded_files, service_providers, service_dependencies, 'test', service)
            children += activate_service(loaded_files, service_providers, service_dependencies, 'build_docker', service)

        # Unknown action
        else:
            raise Exception("Unknown command '%s'" % command)

        service_dependencies[node] = children

    return [node]

###############################################################################

def find_symlinked_directories():
    symlinks = []
    for line in common.run_shell_command("for f in $(find . -type l); do echo \"$f $(ls -l $f | sed -e 's/.* -> //')\"; done").split('\n'):
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

###############################################################################

def look_for_changed_directories():
    if common.force_full_deploy:
        return None
    if common.target is None:
        tag = common.get_tag_name()
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
    # Skip if already loaded or black listed
    if file in loaded_files or file in blacklist:
        return

    # Load YAML and check version
    try:
        with open(file, 'r') as stream:
            data = yaml.load(stream)
    except yaml.parser.ParserError as e:
        raise DMakeException(str(e))

    # Get version
    if 'dmake_version' not in data:
        raise DMakeException("Missing field 'dmake_version' in %s" % file)
    version = str(data['dmake_version'])
    if version not in ['0.1']:
        raise DMakeException("Incorrect version '%s'" % str(data['dmake_version']))

    # Load appropriate version
    if version == '0.1':
        dmake_file = v0_1.DMakeFile(file, data)
    else:
        raise DMakeException("Unknown dmake version '%s', you should consider upgrading dmake." % version)
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
            dmake_file.docker.__fields__['root_image'] = loaded_files[ref].docker.get_docker_base_image_name_tag()
        else:
            dmake_file.docker.__fields__['root_image'] = dmake_file.docker.root_image.full_name()

        # If a base image is declared
        root_image = dmake_file.docker.root_image
        base_image = dmake_file.docker.get_docker_base_image_name_tag()
        if root_image != base_image:
            add_service_provider(service_providers, base_image, file)
            service_dependencies[('base', base_image)] = [('base', root_image)]

    if common.is_string(dmake_file.env):
        ref = dmake_file.env
        load_dmake_file(loaded_files, blacklist, service_providers, service_dependencies, ref)
        if common.is_string(loaded_files[ref].env):
            raise DMakeException('Circular references: trying to load %s which is already loaded.' % ref)
        dmake_file.__fields__['env'] = loaded_files[ref].env
