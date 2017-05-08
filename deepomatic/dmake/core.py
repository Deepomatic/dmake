import os, sys

import deepomatic.dmake.common as common
import deepomatic.dmake.loader as loader
from deepomatic.dmake.common import DMakeException, append_command
from deepomatic.dmake.action import ActionManager
import generator

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

def make(root_dir, sub_dir, command, app, options):
    common.init(command, root_dir, app, options)

    if common.command == "stop":
        common.run_shell_command("docker rm -f `docker ps -q -f name=%s.%s.%s`" % (app, common.branch, common.build_id))
        return

    # Load dmake files
    service_managers = loader.load_dmake_files()

    # Create action managers
    has_services = False
    action_managers = {}
    for a, service_manager in service_managers.items():
        action_managers[a] = ActionManager(service_manager)
        if len(service_manager.get_services()) > 0:
            has_services = True
    if not has_services:
        raise DMakeException('No defined service. Nothing to do.')

    # Filter by app, auto-discovers app by path if not given
    def find_services(filter_path = '', filter_app = None):
        services = []
        for a, service_manager in service_managers.items():
            for s, service in service_manager.get_services().items():
                if str(service.get_dmake_file()).startswith(filter_path) and \
                   (filter_app is None or filter_app == a or filter_app == s):
                    services.append((a, s))
        return services

    if app == "*":
        filtered_services = find_services()
    elif app == "" or app is None: # Discover by path
        filtered_services = find_services(sub_dir)
    else:
        app = app.split('/')
        n = len(app)
        if n > 2:
            raise DMakeException('Cannot have more than one slash in the app name')
        elif n == 2:
            if app[0] in service_managers and \
               app[1] in service_managers[app[0]].get_services():
                filtered_services = [app]
            else:
                filtered_services = []
        else:
            filtered_services = find_services(sub_dir, app[0])

    if len(filtered_services) == 0:
        raise DMakeException('Could not find any service matching the requested pattern.')

    if common.command in ["shell"] and len(filtered_services) > 1:
        filtered_services = map(lambda s: s[0] + '/' + s[1], filtered_services)
        filtered_services = map(lambda s: '- ' + s, filtered_services)
        filtered_services = '\n'.join(filtered_services)
        raise DMakeException('More than one service matches the requested pattern:\n%s' % filtered_services)

    # Generate commands
    action_map = {
        'shell':  'ShellCommand',
        'test':   'TestCommand',
        'deploy': 'DeployCommand',
    }
    if common.command in action_map:
        action = action_map[common.command]
    else:
        raise Exception('Unhandled action')
    for app, service in filtered_services:
        action_managers[app].request(action, service)

    sys.exit(0)


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


    # Register all apps and services in the repo
    docker_links = {}
    services = {}
    for file, dmake_file in loaded_files.items():
        if dmake_file.env is not None and dmake_file.env.source is not None:
            try:
                common.pull_config_dir(os.path.dirname(dmake_file.env.source))
            except common.NotGitRepositoryException as e:
                common.logger.warning('Not a Git repository: %s' % (dmake_file.env.source))

        app_name = dmake_file.get_app_name()
        if app_name not in docker_links:
            docker_links[app_name] = {}
        if app_name not in services:
            services[app_name] = {}

        app_services = services[app_name]
        for service in dmake_file.get_services():
            needs = ["%s/%s" % (app_name, sa) for sa in service.needed_services]
            full_service_name = "%s/%s" % (app_name, service.service_name)
            if service.service_name in app_services:
                raise DMakeException("Duplicated sub-app name: '%s'" % full_service_name)
            add_service_provider(service_providers, full_service_name, file, needs)
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
                file, _ = service_providers[full_service_name]
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
    append_command(all_commands, 'env', var = "BUILD", value = common.build_id)
    append_command(all_commands, 'env', var = "BRANCH", value = common.branch)
    append_command(all_commands, 'env', var = "DMAKE_TMP_DIR", value = common.tmp_dir)

    for stage, commands in ordered_build_files:
        if len(commands) > 0:
            append_command(all_commands, 'stage', name = stage, concurrency = 1 if stage == "Deploying" else None)
        for (command, service), order in commands:
            append_command(all_commands, 'sh', shell = 'echo "Running %s @ %s"' % (command, service))
            if command == 'build':
                dmake_file = loaded_files[service]
            else:
                file, _ = service_providers[service]
                dmake_file = loaded_files[file]
            app_name = dmake_file.get_app_name()
            links = docker_links[app_name]

            try:
                if command == "base":
                    dmake_file.generate_base(all_commands)
                elif command == "shell":
                    dmake_file.generate_shell(all_commands, service, links)
                elif command == "test":
                    dmake_file.generate_test(all_commands, service, links)
                elif command == "run":
                    dmake_file.generate_run(all_commands, service, links)
                elif command == "run_link":
                    dmake_file.generate_run_link(all_commands, service, links)
                elif command == "build":
                    dmake_file.generate_build(all_commands)
                elif command == "build_docker":
                    dmake_file.generate_build_docker(all_commands, service)
                elif command == "deploy":
                    dmake_file.generate_deploy(all_commands, service, links)
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
    if common.command == "deploy" and not common.is_pr:
        append_command(all_commands, 'git_tag', tag = common.get_tag_name())

    # Generate output
    if common.is_local:
        file_to_generate = os.path.join(common.tmp_dir, "DMakefile")
    else:
        file_to_generate = "DMakefile"
    generator.generate(file_to_generate, all_commands)
    common.logger.info("Output has been written to %s" % file_to_generate)

    if common.command == "deploy" and common.is_local:
        r = common.read_input("Careful ! Are you sure you want to deploy ? [Y/n] ")
        if r.lower() != 'y' and r != "":
            print('Aborting')
            sys.exit(0)

    # If on local, run the commands
    if common.is_local:
        result = os.system('bash %s' % file_to_generate)
        do_clean = True
        if result != 0 and common.command in ['run', 'shell', 'test']:
            r = common.read_input("An error was detected. DMake will stop. The script directory is : %s.\nDo you want to stop all the running containers? [Y/n] " % common.tmp_dir)
            if r.lower() != 'y' and r != "":
                do_clean = False
        if do_clean:
            os.system('dmake_clean')


