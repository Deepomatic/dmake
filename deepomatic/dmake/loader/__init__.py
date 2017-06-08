import os
import yaml
import deepomatic.dmake.common as common
from   deepomatic.dmake.common import DMakeException
import v0_1

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

# TODO
# def find_active_files(loaded_files, service_providers, service_dependencies, sub_dir, command):
#     changed_dirs = look_for_changed_directories()
#     if changed_dirs is None:
#         common.logger.info("Forcing full re-build")

#     for file_name, dmake in loaded_files.items():
#         if not file_name.startswith(sub_dir):
#             continue
#         root = os.path.dirname(file_name)
#         active = False
#         if changed_dirs is None:
#             active = True
#         else:
#             for d in changed_dirs:
#                 if d.startswith(root):
#                     active = True

#         if active:
#             activate_file(loaded_files, service_providers, service_dependencies, command, file_name)

###############################################################################

def load_dmake_file(blacklist, loaded_files, service_managers, file):
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
    if version == '0.1':
        dmake_file = v0_1.DMakeFile(service_managers, file, data)
    else:
        raise DMakeException("Unknown dmake version '%s', you should consider upgrading dmake." % version)
    loaded_files[file] = dmake_file

    # Blacklist should be on child file because they are loaded this way
    for bl in dmake_file.get_black_list():
        blacklist.append(bl)

###############################################################################

def load_dmake_files():
    build_files = common.run_shell_command("find . -name dmake.yml").split("\n")
    build_files = filter(lambda f: len(f.strip()) > 0, build_files)
    build_files = [file[2:] for file in build_files]
    # Important: for black listed files: we load file in order from root to deepest file
    build_files = sorted(build_files, key = lambda path: len(os.path.dirname(path)))

    # Load build files
    if len(build_files) == 0:
        raise DMakeException('No dmake.yml file found !')

    # Load all dmake.yml files (except those blacklisted)
    blacklist = []
    loaded_files = {}
    service_managers = {}
    for file in build_files:
        load_dmake_file(blacklist, loaded_files, service_managers, file)

    return service_managers, loaded_files
