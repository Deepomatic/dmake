import os, sys
import yaml

import deepomatic.dmake.common as common
from   deepomatic.dmake.common import DMakeException
from   deepomatic.dmake.deepobuild import DMakeFile, append_command

tag_push_error_msg = "Unauthorized to push the current state of deployment to git server. If the repository belongs to you, please check that you have declared a SSH credentials named 'dmake'"

###############################################################################

def look_for_changed_directories():
    if common.is_manual_trigger:
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

    #common.logger.info("Changed files:")
    #common.logger.info(output)

    changed_dirs = set()
    for file in [file.strip() for file in output.split('\n')]:
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
    build_files = common.run_shell_command("find . -name dmake.yml").split("\n")
    build_files = filter(lambda f: len(f.strip()) > 0, build_files)
    build_files = [file[2:] for file in build_files]
    return build_files

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

    dmake = loaded_files[file]
    if command == 'base':
        root_image = dmake.docker.root_image
        base_image = dmake.docker.get_docker_base_image_name_tag()
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
        for service in dmake.get_services():
            full_service_name = "%s/%s" % (dmake.app_name, service.service_name)
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
    if node not in service_dependencies:
        file, needs = service_providers[service]
        if command == 'base':
            children = activate_file(loaded_files, service_providers, service_dependencies, 'base', file)
        elif command == 'shell':
            children = []
            if getattr(common.options, 'dependencies', None) and needs is not None:
                for n in needs:
                    children += activate_service(loaded_files, service_providers, service_dependencies, 'run', n)
                children += activate_link(loaded_files, service_providers, service_dependencies, service)
            children += activate_file(loaded_files, service_providers, service_dependencies, 'base', file)
        elif command == 'test':
            children = []
            if getattr(common.options, 'dependencies', None) and needs is not None:
                for n in needs:
                    children += activate_service(loaded_files, service_providers, service_dependencies, 'run', n)
            children += activate_file(loaded_files, service_providers, service_dependencies, 'build', file)
            if getattr(common.options, 'dependencies', None):
                children += activate_link(loaded_files, service_providers, service_dependencies, service)
        elif command == 'build_docker':
            children = []
        elif command == 'run':
            children = activate_service(loaded_files, service_providers, service_dependencies, 'build_docker', service)
            if getattr(common.options, 'dependencies', None) and needs is not None:
                for n in needs:
                    children += activate_service(loaded_files, service_providers, service_dependencies, 'run', n)
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
    try:
        with open(file, 'r') as stream:
            data = yaml.load(stream)
    except yaml.parser.ParserError as e:
        raise DMakeException(str(e))
    if 'dmake_version' not in data:
        raise DMakeException("Missing field 'dmake_version' in %s" % file)
    version = str(data['dmake_version'])
    if version not in ['0.1']:
        raise DMakeException("Incorrect version '%s'" % str(data['dmake_version']))

    # Load appropriate version (TODO: versionning)
    if version == '0.1':
        dmake = DMakeFile(file, data)
    loaded_files[file] = dmake

    # Blacklist should be on child file because they are loaded this way
    for bl in dmake.blacklist:
        blacklist.append(bl)

    for link in dmake.docker_links:
        add_service_provider(service_providers, 'links/%s/%s' % (dmake.get_app_name(), link.link_name), file)

    # Unroll docker image references
    if common.is_string(dmake.docker):
        ref = dmake.docker
        load_dmake_file(loaded_files, blacklist, service_providers, service_dependencies, ref)
        dmake.__fields__['docker'] = loaded_files[ref].docker
    else:
        if common.is_string(dmake.docker.root_image):
            ref = dmake.docker.root_image
            load_dmake_file(loaded_files, blacklist, service_providers, service_dependencies, ref)
            dmake.docker.__fields__['root_image'] = loaded_files[ref].docker.get_docker_base_image_name_tag()
        else:
            dmake.docker.__fields__['root_image'] = dmake.docker.root_image.full_name()

        # If a base image is declared
        root_image = dmake.docker.root_image
        base_image = dmake.docker.get_docker_base_image_name_tag()
        if root_image != base_image:
            add_service_provider(service_providers, base_image, file)
            service_dependencies[('base', base_image)] = [('base', root_image)]

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
    file.write('{ ->\n')
    if common.build_description is not None:
        file.write("currentBuild.description = '%s'\n" % common.build_description.replace("'", "\\'"))
    file.write('node {\n')
    file.write('try {\n')

    # Check crendentials
    file.write("try {withCredentials([[$class: 'UsernamePasswordMultiBinding', credentialsId: 'dmake-http', usernameVariable: '_', passwordVariable: '__']]) {}}\n")
    file.write("""catch(error) {\nsh('echo "WARNING: Jenkins credentials \\'dmake-http\\' are not defined: you won\\'t be able to deploy only the part of your app that have changed."')\n}\n""")

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
            url = common.repo_url
            if url is not None and (url.startswith('https://') or url.startswith('http://')):
                i = url.find(':')
                prefix = url[:i]
                host = url[(i + 3):]
                file.write("sh('git tag --force %s')\n" % kwargs['tag'])
                file.write('try {\n')
                file.write("withCredentials([[$class: 'UsernamePasswordMultiBinding', credentialsId: 'dmake-http', usernameVariable: 'GIT_USERNAME', passwordVariable: 'GIT_PASSWORD']]) {\n")
                file.write("sh('env')\n")
                file.write('try {\n')
                file.write("sh('git push %s://${GIT_USERNAME}:${GIT_PASSWORD}@%s --force origin refs/tags/%s')\n" % (prefix, host, kwargs['tag']))
                file.write("""} catch(error) {\nsh('echo "%s"')\n}\n""" % tag_push_error_msg.replace("'", "\\'"))
                file.write("}\n")
                file.write("""} catch(error) {\nsh('echo "Credentials \\'dmake-http\\' are not defined, skipping tag pushing."')\n}\n""")
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
            raise DMakeException("Unknown command %s" % cmd)

    file.write('}\n')
    file.write('finally {\n')
    file.write('sh("dmake_clean")\n')
    file.write('sh("sudo chown jenkins:jenkins . -R")\n')
    file.write('}\n}}\n')

###############################################################################

def generate_command_bash(file, cmds):
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

def make(root_dir, sub_dir, dmake_command, app, options):
    if 'DMAKE_TMP_DIR' in os.environ:
        del os.environ['DMAKE_TMP_DIR']
    common.init(dmake_command, root_dir, options)

    if dmake_command == "stop":
        common.run_shell_command("docker rm -f `docker ps -q -f name=%s.%s.%s`" % (app, common.branch, common.build_id))
        return

    # Format args
    auto_complete = False
    auto_completed_app = None
    if app is not None:
        n = len(app.split('/'))
        if n > 2:
            raise DMakeException('Cannot have more than one slash in the app name')
        auto_complete = n == 1
        if auto_complete:
            auto_completed_app = None
            auto_complete_is_app = None
        else:
            auto_completed_app = app

    # Load build files
    build_files = load_dmake_files_list()
    if len(build_files) == 0:
        raise DMakeException('No dmake.yml file found !')

    # Sort by increasing length to make sure we load parent files first
    sorted(build_files, key = lambda file: len(file))

    # Load all dmake.yml files (except those blacklisted)
    blacklist = []
    loaded_files = {}
    service_providers = {}
    service_dependencies = {}
    for file in build_files:
        load_dmake_file(loaded_files, blacklist, service_providers, service_dependencies, file)

    # Remove black listed files
    for f in blacklist:
        if f in loaded_files:
            del loaded_files[f]

    # Register all apps and services in the repo
    docker_links = {}
    services = {}
    for file, dmake in loaded_files.items():
        app_name = dmake.get_app_name()
        if app_name not in docker_links:
            docker_links[app_name] = {}
        if app_name not in services:
            services[app_name] = {}

        if auto_complete and app_name == app:
            if auto_completed_app is None:
                auto_completed_app = app

        app_services = services[app_name]
        for service in dmake.get_services():
            needs = ["%s/%s" % (app_name, sa) for sa in service.needed_services]
            full_service_name = "%s/%s" % (app_name, service.service_name)
            if service.service_name in app_services:
                raise DMakeException("Duplicated sub-app name: '%s'" % full_service_name)
            add_service_provider(service_providers, full_service_name, file, needs)
            app_services[service.service_name] = service

            if auto_complete and service.service_name == app:
                if auto_completed_app is None:
                    auto_completed_app = full_service_name
                    auto_complete_is_app = False
                else:
                    raise DMakeException("Ambigous app name '%s' is matching sub-app '%s' and %sapp '%s'" % (app, full_service_name, "" if auto_complete_is_app else "sub-", auto_completed_app))

        app_links = docker_links[app_name]
        for link in dmake.get_docker_links():
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
    if dmake_command == "run" and is_app_only:
        common.options.dependencies = True

    if auto_completed_app is None:
        # Find file where changes have happened
        find_active_files(loaded_files, service_providers, service_dependencies, sub_dir, dmake_command)
    else:
        if is_app_only: # app only
            if dmake_command == 'shell':
                raise DMakeException("Could not find sub-app '%s'" % app)
            active_file = set()
            app_services = services[auto_completed_app]
            for service in app_services.values():
                full_service_name = "%s/%s" % (auto_completed_app, service.service_name)
                file, _ = service_providers[full_service_name]
                active_file.add(file)
            for file in active_file:
                activate_file(loaded_files, service_providers, service_dependencies, dmake_command, file)
        else:
            activate_service(loaded_files, service_providers, service_dependencies, dmake_command, auto_completed_app)

    # check services circularity
    sorted_leaves = check_no_circular_dependencies(service_dependencies)
    sorted_leaves = filter(lambda a_b__c: a_b__c[0][0] == dmake_command, sorted_leaves)
    build_files_order = order_dependencies(service_dependencies, sorted_leaves)

    # Sort by order
    ordered_build_files = sorted(build_files_order.items(), key = lambda file_order: file_order[1])

    # Separate into base / build / tests / deploy
    n = len(ordered_build_files)
    base   = list(filter(lambda a_b__c: a_b__c[0][0] in ['base'], ordered_build_files))
    build  = list(filter(lambda a_b__c: a_b__c[0][0] in ['build', 'build_docker'], ordered_build_files))
    test   = list(filter(lambda a_b__c: a_b__c[0][0] in ['test', 'shell', 'run_link', 'run'], ordered_build_files))
    deploy = list(filter(lambda a_b__c: a_b__c[0][0] in ['deploy'], ordered_build_files))
    if len(base) + len(build) + len(test) + len(deploy) != len(ordered_build_files):
        raise Exception('Something went wrong when reorganizing build steps. One of the commands is probably missing.')

    ordered_build_files = [('Building Docker', base),
                           ('Building App', build),
                           ('Testing App', test)]

    if not common.is_pr:
        ordered_build_files.append(('Deploying', list(deploy)))

    # Display commands
    common.logger.info("Here is the plan:")
    for stage, commands in ordered_build_files:
        if len(commands) > 0:
            common.logger.info("## %s ##" % (stage))
        for (command, service), order in commands:
            # Sanity check
            sub_task_orders = [build_files_order[a] for a in service_dependencies[(command, service)]]
            if any(map(lambda o: order <= o, sub_task_orders)):
                raise DMakeException('Bad ordering')
            common.logger.info("- %s @ %s" % (command, service))

    # Generate the list of command to run
    all_commands = []
    append_command(all_commands, 'env', var = "REPO", value = common.repo)
    append_command(all_commands, 'env', var = "COMMIT", value = common.commit_id)
    append_command(all_commands, 'env', var = "BRANCH", value = common.branch)
    append_command(all_commands, 'env', var = "ENV_TYPE", value = common.env_type)
    append_command(all_commands, 'env', var = "DMAKE_TMP_DIR", value = common.tmp_dir)

    for stage, commands in ordered_build_files:
        if len(commands) > 0:
            append_command(all_commands, 'stage', name = stage, concurrency = 1 if stage == "Deploying" else None)
        for (command, service), order in commands:
            append_command(all_commands, 'sh', shell = 'echo "Running %s @ %s"' % (command, service))
            if command == 'build':
                dmake = loaded_files[service]
            else:
                file, _ = service_providers[service]
                dmake = loaded_files[file]
            app_name = dmake.get_app_name()
            links = docker_links[app_name]

            try:
                if command == "base":
                    dmake.generate_base(all_commands)
                elif command == "shell":
                    dmake.generate_shell(all_commands, service, links)
                elif command == "test":
                    dmake.generate_test(all_commands, service, links)
                elif command == "run":
                    dmake.generate_run(all_commands, service, links)
                elif command == "run_link":
                    dmake.generate_run_link(all_commands, service, links)
                elif command == "build":
                    dmake.generate_build(all_commands)
                elif command == "build_docker":
                    dmake.generate_build_docker(all_commands, service)
                elif command == "deploy":
                    dmake.generate_deploy(all_commands, service, links)
                else:
                   raise Exception("Unkown command '%s'" % command)
            except DMakeException as e:
                print(('ERROR in file %s:\n' % file) + str(e))
                sys.exit(1)

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
    if dmake_command == "deploy" and not common.is_pr:
        append_command(all_commands, 'git_tag', tag = get_tag_name())

    # Generate output
    if common.is_local:
        file_to_generate = os.path.join(common.tmp_dir, "DMakefile")
    else:
        file_to_generate = "DMakefile"
    generate_command(file_to_generate, all_commands)
    common.logger.info("Output has been written to %s" % file_to_generate)

    if dmake_command == "deploy" and common.is_local:
        r = common.read_input("Careful ! Are you sure you want to deploy ? [Y/n] ")
        if r.lower() != 'y' and r != "":
            print('Aborting')
            sys.exit(0)

    # If on local, run the commands
    if common.is_local:
        result = os.system('bash %s' % file_to_generate)
        if result != 0 or dmake_command != 'run':
            os.system('dmake_clean')


