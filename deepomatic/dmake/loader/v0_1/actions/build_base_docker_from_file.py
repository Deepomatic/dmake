import os

from deepomatic.dmake.action import Action
import deepomatic.dmake.common as common

###############################################################################

class BuildBaseDockerFromFile(Action):
    """
    Builds a docker image from a dmake file
    """
    stage = 'base'
    use_service = False

    def _set_context_(self, base_name, external):
        self.context.set('tmp_base_image', {
            'name': base_name,
            'external': external
        })

    def _generate_(self, dmake_file, _):
        docker = dmake_file.serializer.docker

        if not docker.base_image.has_value():
            self._set_context_(docker.root_image.name + ':' + docker.root_image.tag, True)
            return
        else:
            image_name = 'tmp-%s:%s-%s' % (dmake_file.get_md5(), common.branch, common.build_id)
            self._set_context_(image_name, False)

        # Make the temporary directory
        tmp_dir = common.run_shell_command('dmake_make_tmp_dir')

        # Copy file and compute their md5
        files_to_copy = []
        for file in docker.base_image.copy_files + docker.base_image.install_scripts:
            files_to_copy.append(file)
        if docker.base_image.python_requirements:
            files_to_copy.append(docker.base_image.python_requirements)
        if docker.base_image.python3_requirements:
            files_to_copy.append(docker.base_image.python3_requirements)

        # Copy file and keep their md5
        md5s = {}
        for file in files_to_copy:
            md5s[file] = common.run_shell_command('dmake_copy_file %s %s' % (os.path.join(dmake_file.get_path(), file), os.path.join(tmp_dir, 'user', file)))

        # Set RUN command
        run_cmd = "cd user"
        for file in docker.base_image.install_scripts:
            run_cmd += " && ./%s" % file

        # Install pip if needed
        if docker.base_image.python_requirements:
            run_cmd += " && bash ../install_pip.sh && pip install --process-dependency-links -r " + docker.base_image.python_requirements
        if docker.base_image.python3_requirements:
            run_cmd += " && bash ../install_pip3.sh && pip3 install --process-dependency-links -r " + docker.base_image.python3_requirements

        # Save the command in a bash file
        file = 'run_cmd.sh'
        with open(os.path.join(tmp_dir, file), 'w') as f:
            f.write(run_cmd)
        md5s[file] = common.run_shell_command('dmake_md5 %s' % os.path.join(tmp_dir, file))

        # FIXME: copy key while #493 is not closed: https://github.com/docker/for-mac/issues/483
        if common.key_file is not None:
            common.run_shell_command('cp %s %s' % (common.key_file, os.path.join(tmp_dir, 'key')))

        # Local environment for temmplates
        local_env = []
        local_env.append("export ROOT_IMAGE=%s" % docker.root_image)
        local_env = ' && '.join(local_env)
        if len(local_env) > 0:
            local_env += ' && '

        # Copy templates
        for file in ["make_base.sh", "config.logrotate", "load_credentials.sh", "install_pip.sh", "install_pip3.sh"]:
            md5s[file] = common.run_shell_command('%s dmake_copy_template docker-base/%s %s' % (local_env, file, os.path.join(tmp_dir, file)))

        # Output md5s for comparison
        with open(os.path.join(tmp_dir, 'md5s'), 'w') as f:
            for md5 in md5s.items():
                f.write('%s %s\n' % md5)

        # Append Docker Base build command
        commands = []
        self.append_command('sh', shell = self.dmake_shell_command(
                        'dmake_build_base_docker',
                        tmp_dir,
                        docker.root_image,
                        image_name))
        return commands

###############################################################################

class BuildBaseDockerFromService(Action):
    stage = 'base'

    def _generate_(self, dmake_file, service):
        if service.get_docker_image_name() is None:
            return

        target_tag = 'base-%s' % common.commit_id
        other_tags = []
        if common.target is not None:
            other_tags.append('base-%s' % common.target)

        self.dmake_shell_command(
            'dmake_check_base_docker',
            service.get_docker_image_name(),
            target_tag,
            *other_tags)

        #base = self.request('BuildBaseDockerFromFile', service)

###############################################################################
