import os
import md5

from deepomatic.dmake.action import Action
import deepomatic.dmake.common as common

###############################################################################

class GetBaseMD5(Action):
    """
    Build a directory with all files needed for the base image
    Returns the base image hash.

    For now (15/05/2017) this is the only way to reconciliate a an image built from a PR.
    Indeed, Jenkins Github Plugin does not allow to get the branch name for a PR.
    """
    stage = 'base'
    use_service = False

    def _set_context_(self, dmake_file, tmpdir, md5, root_image):
        self.context.set('tmp_base_image', {
            'dmake_file': dmake_file,
            'tmpdir': tmpdir,
            'md5': md5,
            'root_image': root_image,
            'base_image_name': 
            'name': base_name,
            'external': external
        })

        self.context.set('tmp_base_dmake_file', tmp_base_dmake_file)
        self.context.set('tmp_base_tmpdir', tmp_base_tmpdir)
        self.context.set('tmp_base_md5', tmp_base_md5)

    def _generate_(self, dmake_file, _):
        docker = dmake_file.serializer.docker

        # If the docker field points to another dmake file, we call this one instead
        # FIXME: What if GetBaseMD5 is not defined ?
        if common.is_string(docker):
            self.merge_context(
                # We require same_build_host because it generate some files
                # FIXME: use build artifact to be cross build hosts
                self.request('GetBaseMD5', dmake_file_path = dmake_file.serializer.docker, same_build_host = True)
            )
            return

        # Get the image of the root image
        # If root image points to another dmake file, we need to build it before
        if common.is_string(docker.root_image):
            # Here, we require 'force_naming' to force a push to a registry to be able 
            # to use the image across multiple build nodes.
            # FIXME: Should we use build artifacts instead to store a temporary image ?
            node = self.request('BuildBaseDockerFromFile', dmake_file_path = docker.root_image, force_naming = True)
            root_image_name = node.context.get('tmp_base_image')['name']
            root_image_id   = node.context.get('tmp_base_image')['id']
        else:
            root_image_name = docker.root_image.name + ':' + docker.root_image.tag
            root_image_id   = common.run_shell_command(
                self.dmake_shell_command('get_last_docker_image_id', root_image_name))

        if not docker.base_image.has_value():
            self._set_context_(str(dmake_file), None, '')
            return

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
        md5s = {
            root_image_name: root_image_id
        }
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

        # Copy templates
        for file in ["make_base.sh", "config.logrotate", "load_credentials.sh", "install_pip.sh", "install_pip3.sh"]:
            md5s[file] = common.run_shell_command('dmake_copy_template docker-base/%s %s' % (file, os.path.join(tmp_dir, file)))

        # Output md5s for comparison
        with open(os.path.join(tmp_dir, 'md5s'), 'w') as f:
            for m in md5s.items():
                f.write('%s %s\n' % m)

        m = md5.new()
        for key_value in md5s.items():
            m.update('%s:%s' % key_value)

        self._set_context_(str(dmake_file), tmp_dir, m.hexdigest())

###############################################################################

class BuildBaseDockerFromFile(Action):
    """
    Builds a docker image from a dmake file in a lazy manner. Only rebuilds if:
        - root image has changed
        - base md5 has changed
    """
    stage = 'base'
    use_service = False

    def _set_context_(self, base_name, external):
        self.context.set('tmp_base_image', {
            'name': base_name,
            'external': external
        })

    def _generate_(self, dmake_file, _, force_naming = False):

        self.merge_context(self.request('GetBaseMD5', same_build_host = True))
        docker = dmake_file.serializer.docker
        image_name = 'auto-%s-%s:tmp-%s' % (common.build_id, dmake_file.get_md5(), self.context.get('tmp_base_md5'))

        # Append Docker Base build command
        self.append_command('sh', shell = 
            self.dmake_shell_command(
                'build_base_docker',
                self.context.get('tmp_base_tmpdir'),
                docker.root_image,
                image_name))

###############################################################################

class BuildBaseDockerFromService(Action):
    stage = 'base'

    def _generate_(self, dmake_file, service):
        self.request('BuildBaseDockerFromFile')



        target_tag = 'base-%s' % common.commit_id
        other_tags = []
        if common.target is not None:
            other_tags.append('base-%s' % common.target)

        code = common.run_shell_command(
            self.dmake_shell_command(
                'check_base_docker',
                service.get_docker_image_name(),
                target_tag,
                *other_tags),
            get_return_code = True)

        if code == 0:
            return

        #base = self.request('BuildBaseDockerFromFile', service.get_name(), same_build_host = True)

###############################################################################
