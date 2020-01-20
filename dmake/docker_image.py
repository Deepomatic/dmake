import os
from abc import abstractmethod

import dmake.common as common
from dmake.common import DMakeException, append_command
from dmake.serializer import FieldSerializer, SerializerMixin, YAML2PipelineSerializer

###############################################################################

def generate_copy_command(commands, tmp_dir, src):
    src = common.join_without_slash(src)
    if src == '':
        src = '.'
    dst = os.path.join(tmp_dir, 'app', src)
    sub_dir = os.path.dirname(common.join_without_slash(dst))
    append_command(commands, 'sh', shell = 'mkdir -p %s && cp -LRf %s %s' % (sub_dir, src, sub_dir))

###############################################################################

class AbstractDockerImage(SerializerMixin):
    """
    This is an abstract class to represent a docker image, either
    built or external.
    TODO: docker images should come in two flavor: 'dev' and 'run' to
    allow to chain proper development and runtime builds.
    TODO: remove `set_service`: a docker image is not tied to a service,
    at least not at this step.
    """

    def set_service(self, service):
        self.service = service

    @abstractmethod
    def get_image_name(self, env=None):
        """
        Return the full image name to use, tag included.
        """
        pass

    @abstractmethod
    def get_base_image_variant(self):
        """
        Return the base variants to use to build this base image
        """
        pass

    @abstractmethod
    def get_source_directories_additional_contexts(self):
        pass

    @abstractmethod
    def is_runnable(self):
        pass

    @abstractmethod
    def generate_build_docker(self, commands, path_dir, docker_base, build):
        pass

    @abstractmethod
    def generate_push_docker(self, commands, service_name, env):
        """
        Generate the commands to push the built image to docker Hub
        """
        pass

###############################################################################

class ExternalDockerImage(AbstractDockerImage):

    def __init__(self, image_name):
        AbstractDockerImage.__init__(self)
        self.image_name = image_name

    def get_image_name(self, env=None):
        return common.eval_str_in_env(self.image_name, env)

    def get_base_image_variant(self):
        """No variant for external image"""
        return None

    def get_source_directories_additional_contexts(self):
        """No additional source context supported"""
        return []

    def is_runnable(self):
        return True

    def generate_build_docker(self, commands, path_dir, docker_base, build):
        """We do not need to do anything"""
        pass

    def generate_push_docker(self, commands, service_name, env):
        """
        This image does not belong to this build process, we do not do anything
        """
        pass

###############################################################################

class ServiceDockerCommonSerializer(YAML2PipelineSerializer, AbstractDockerImage):
    name             = FieldSerializer("string", optional = True, help_text = "Name of the docker image to build. By default it will be {:app_name}-{:service_name}. If there is no docker user, it won be pushed to the registry. You can use environment variables.")
    base_image_variant = FieldSerializer(["string", "array"], optional = True, child = "string", help_text = "Specify which `base_image` variants are used as `base_image` for this service. Array: multi-variant service. Default: first 'docker.base_image'.")
    source_directories_additional_contexts = FieldSerializer("array", child = "string", default = [], example = ['../web'], help_text = "NOT RECOMMENDED. Additional source directories contexts for changed services auto detection in case of build context going outside of the dmake.yml directory.")
    check_private    = FieldSerializer("bool", default = True, help_text = "Check that the docker repository is private before pushing the image.")
    tag              = FieldSerializer("string", optional = True, help_text = "Tag of the docker image to build. By default it will be '[{:variant}-]{:branch_name}-{:build_id}', sanitized and made unique with a hash suffix if needed")

    def get_source_directories_additional_contexts(self):
        return self.source_directories_additional_contexts

    def get_image_name(self, env=None, latest=False):
        if env is None:
            env = {}
        # name
        if self.name is None:
            name = self.service.original_service_name.replace('/', '-')
        else:
            name = common.eval_str_in_env(self.name, env)
        # tag
        if self.tag is None:
            tag = common.image_tag_prefix
            if latest:
                tag += "-latest"
            else:
                if common.build_id is not None:
                    tag += "-%s" % common.build_id
        else:
            tag = self.tag
        if self.service.is_variant:
            tag = "%s-%s" % (tag, self.service.variant)
        # image name
        image_name = name + ":" + tag
        return image_name

    def get_base_image_variant(self):
        return self.base_image_variant

    def generate_push_docker(self, commands, service_name, env):
        image_name = self.get_image_name(env=env)
        # When deploying, we need to push the image. We make sure that the image has a user
        if len(image_name.split('/')) == 1:
            image_name_without_tag = image_name.split(':')[0]
            raise DMakeException("Service '{}' declares a docker image without a user name in config::docker_image::name so I cannot deploy it. I suggest to change it to 'your_company/{}'".format(service_name, image_name_without_tag))

        check_private_flag = "1" if self.check_private else "0"
        append_command(commands, 'sh', shell='dmake_push_docker_image "%s" "%s"' % (image_name, check_private_flag))
        image_latest = self.get_image_name(env=env, latest=True)
        append_command(commands, 'sh', shell='docker tag %s %s && dmake_push_docker_image "%s" "%s"' % (image_name, image_latest, image_latest, check_private_flag))

###############################################################################

class ServiceDockerV1Serializer(ServiceDockerCommonSerializer):
    # v1: dmake generated Dockerfile
    workdir          = FieldSerializer("dir", optional = True, help_text = "Working directory of the produced docker file, must be an existing directory. By default it will be directory of the dmake file.")
    copy_directories = FieldSerializer("array", child = "dir", default = [], help_text = "Directories to copy in the docker image.")
    install_script   = FieldSerializer("file", child_path_only = True, executable = True, optional = True, example = "install.sh", help_text = "The install script (will be run in the docker). It has to be executable.")
    entrypoint       = FieldSerializer("file", child_path_only = True, executable = True, optional = True, help_text = "Set the entrypoint of the docker image generated to run the app.")
    start_script     = FieldSerializer("file", child_path_only = True, executable = True, optional = True, example = "start.sh", help_text = "The start script (will be run in the docker). It has to be executable.")

    def is_runnable(self):
        return self.start_script is not None

    def generate_build_docker(self, commands, path_dir, docker_base, build):
        image_name = self.get_image_name()
        tmp_dir = common.make_tmp_dir('service_docker_v1_build_{}'.format(common.sanitize_name(image_name)))
        common.run_shell_command('mkdir %s' % os.path.join(tmp_dir, 'app'))

        generate_copy_command(commands, tmp_dir, path_dir)
        for d in self.copy_directories:
            generate_copy_command(commands, tmp_dir, os.path.join(path_dir, '..', d))

        mount_point = docker_base.mount_point
        docker_base_image = docker_base.get_docker_base_image(self.base_image_variant)
        dockerfile = os.path.join(tmp_dir, 'Dockerfile')
        with open(dockerfile, 'w') as f:
            f.write('FROM %s\n' % docker_base_image)
            f.write("ADD app %s\n" % mount_point)

            if self.workdir is not None:
                workdir = self.workdir
            else:
                workdir = path_dir
            workdir = os.path.join(mount_point, workdir)
            f.write('WORKDIR %s\n' % workdir)

            for port in self.service.config.ports:
                f.write('EXPOSE %d\n' % port.container_port)

            if build.has_value():
                for key, value in build.env.items():
                    if value:
                        f.write('ENV %s %s\n' % (key, common.wrap_cmd(value)))
                    else:
                        # docker 17.06.1-ce rejects "ENV foo ", special case to passe empty value
                        f.write('ENV %s=""\n' % (key))
                f.write('ENV DMAKE_BUILD_TYPE %s\n' % (common.get_dmake_build_type()))

                cmds = []
                for cmd in build.commands:
                    cmds += cmd
                if len(cmds) > 0:
                    cmd = ' && '.join(cmds)
                    f.write('RUN cd %s && %s\n' % (workdir, cmd))

            if self.install_script is not None:
                f.write('RUN cd %s && %s\n' % (workdir, os.path.join(mount_point, path_dir, self.install_script)))

            if self.start_script is not None:
                f.write('CMD ["%s"]\n' % os.path.join(mount_point, path_dir, self.start_script))

            if self.entrypoint is not None:
                f.write('ENTRYPOINT ["%s"]\n' % os.path.join(mount_point, path_dir, self.entrypoint))

        append_command(commands, 'sh', shell = 'dmake_build_docker "%s" "%s"' % (tmp_dir, image_name))

###############################################################################

class ServiceDockerBuildSerializer(YAML2PipelineSerializer):
    context    = FieldSerializer("dir", help_text = "Docker build context directory.", example = '.')
    dockerfile = FieldSerializer("string", optional = True, help_text = "Alternate Dockerfile, relative path to `context` directory.", example = 'deploy/Dockerfile')
    args       = FieldSerializer("dict", child = "string", default = {}, help_text = "Add build arguments, which are environment variables accessible only during the build process. Higher precedence than `.build.env`.", example = {'BUILD': '${BUILD}'})
    labels     = FieldSerializer('dict', child="string", default = {}, help_text = "Add metadata to the resulting image using Docker labels. It's recommended that you use reverse-DNS notation to prevent your labels from conflicting with those used by other software.", example={'vendor': 'deepomatic', 'build': '${BUILD}'})
    target     = FieldSerializer("string", optional = True, help_text = "Build the specified stage as defined inside the Dockerfile. See the [multi-stage build docs](https://docs.docker.com/engine/userguide/eng-image/multistage-build/) for details.", example = 'runtime')

    def _validate_(self, file, needed_migrations, data, field_name):
        # also accept simple variant where data is a string: the `context` directory
        if common.is_string(data):
            data = {'context': data}
        result = super(ServiceDockerBuildSerializer, self)._validate_(file, needed_migrations=needed_migrations, data=data, field_name=field_name)
        return result

    def _serialize_(self, commands, path_dir, image_name, build_args):
        # variables substitution from dmake process environment
        common.eval_values_in_env(self.args, strict=True)
        common.eval_values_in_env(self.labels, strict=True)

        program = 'dmake_build_docker'
        args = [self.context, image_name]
        # dockerfile
        if self.dockerfile:
            # in docker-compose the `dockerfile` path is relative to the `context`, we do the same in dmake; but in `docker image build the `--file` path is relative to CWD, not to `context`.
            dockerfile_path = os.path.join(self.context, self.dockerfile)
            args += ["--file=%s" % (dockerfile_path)]
        # build arg
        build_args.update(self.args)
        args += ["--build-arg=%s=%s" % (key, value) for key, value in build_args.items()]
        # labels
        args += ["--label=%s=%s" % (key, value) for key, value in self.labels.items()]
        # target
        if self.target:
            args.append("--target=%s" % (self.target))
        cmd = '%s %s' % (program, ' '.join(map(common.wrap_cmd, args)))
        append_command(commands, 'sh', shell = cmd)

###############################################################################

class ServiceDockerV2Serializer(ServiceDockerCommonSerializer):
    # v2: user provided Dockerfile
    build            = ServiceDockerBuildSerializer(help_text = "Docker build options for service built using user-provided Dockerfile (ignore `.build.commands`), like in Docker Compose files.`")

    def is_runnable(self):
        # assume the user-provided Dockerfile is a runnable service
        return True

    def generate_build_docker(self, commands, path_dir, docker_base, build):
        image_name = self.get_image_name()
        base_image_name = docker_base.get_docker_base_image(self.base_image_variant)
        build_args = {
            'BASE_IMAGE': base_image_name,
            'WORKDIR': os.path.join(docker_base.mount_point, path_dir),
        }
        self.build._serialize_(commands, path_dir, image_name, build_args)

###############################################################################

class DockerImageFieldSerializer(FieldSerializer):

    def __init__(self):
        FieldSerializer.__init__(self, ["string", ServiceDockerV1Serializer(), ServiceDockerV2Serializer()], allow_null = True, help_text = "Docker image to use for running and deploying.")

    def _validate_(self, *args, **kwargs):
        # We hook the validation method to transform the string value in "ExternalDockerImage"
        value = FieldSerializer._validate_(self, *args, **kwargs)
        if common.is_string(value):
            # TODO: normalize this, either we store the value internally, or we return it
            self.value = ExternalDockerImage(value)
        return self.value
