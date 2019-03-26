import os
import copy
import json
import uuid
import importlib
import re
import requests.exceptions
from string import Template
from dmake.serializer import ValidationError, FieldSerializer, YAML2PipelineSerializer
import dmake.common as common
from dmake.common import DMakeException, SharedVolumeNotFoundException
import dmake.kubernetes as k8s_utils
import dmake.docker_registry as docker_registry

###############################################################################

def append_command(commands, cmd, prepend = False, **args):
    def check_cmd(args, required, optional = []):
        for a in required:
            if a not in args:
                raise DMakeException("%s is required for command %s" % (a, cmd))
        for a in args:
            if a not in required and a not in optional:
                raise DMakeException("Unexpected argument %s for command %s" % (a, cmd))
    if cmd == "stage":
        check_cmd(args, ['name', 'concurrency'])
    elif cmd == "stage_end":
        check_cmd(args, [])
    elif cmd == "lock":
        check_cmd(args, ['label'])
    elif cmd == "lock_end":
        check_cmd(args, [])
    elif cmd == "timeout":
        check_cmd(args, ['time'])
    elif cmd == "timeout_end":
        check_cmd(args, [])
    elif cmd == "echo":
        check_cmd(args, ['message'])
    elif cmd == "sh":
        check_cmd(args, ['shell'])
    elif cmd == "read_sh":
        check_cmd(args, ['var', 'shell'], optional = ['fail_if_empty'])
        if 'fail_if_empty' not in args:
            args['fail_if_empty'] = False
    elif cmd == "env":
        check_cmd(args, ['var', 'value'])
    elif cmd == "git_tag":
        check_cmd(args, ['tag'])
    elif cmd == "junit":
        check_cmd(args, ['report', 'service_name', 'mount_point'])
    elif cmd == "cobertura":
        check_cmd(args, ['report', 'service_name', 'mount_point'])
    elif cmd == "publishHTML":
        check_cmd(args, ['directory', 'index', 'title', 'service_name', 'mount_point'])
    else:
        raise DMakeException("Unknown command %s" % cmd)
    cmd = (cmd, args)
    if prepend:
        commands.insert(0, cmd)
    else:
        commands.append(cmd)

###############################################################################

def generate_copy_command(commands, tmp_dir, src):
    src = common.join_without_slash(src)
    if src == '':
        src = '.'
    dst = os.path.join(tmp_dir, 'app', src)
    sub_dir = os.path.dirname(common.join_without_slash(dst))
    append_command(commands, 'sh', shell = 'mkdir -p %s && cp -LRf %s %s' % (sub_dir, src, sub_dir))

###############################################################################

def generate_env_file(tmp_dir, env):
    while True:
        file = os.path.join(tmp_dir, 'env.txt.%s' % uuid.uuid4())
        if not os.path.isfile(file):
            break
    with open(file, 'w') as f:
        for key, value in env.items():
            f.write('%s=%s\n' % (key, value))
    return file

###############################################################################

def get_docker_run_gpu_cmd_prefix(need_gpu, service_type, service_name):
    prefix = ''
    if need_gpu:
        if common.no_gpu:
            common.logger.info("GPU needed by %s '%s' but DMAKE_NO_GPU set: trying without GPU." % (service_type, service_name))
            prefix = 'DMAKE_DOCKER_RUN_WITH_GPU=none '
            pass
        else:
            common.need_gpu = True
            prefix = 'DMAKE_DOCKER_RUN_WITH_GPU=yes '
    return prefix

# ###############################################################################

class EnvBranchSerializer(YAML2PipelineSerializer):
    source    = FieldSerializer('string', optional=True, help_text='Source a bash file which defines the environment variables before evaluating the strings of environment variables passed in the *variables* field. It might contain environment variables itself.')
    variables = FieldSerializer('dict', child="string", default={}, help_text="Defines environment variables used for the services declared in this file. You might use pre-defined environment variables (or variables sourced from the file defined in the *source* field).", example={'ENV_TYPE': 'dev'})

    def get_replaced_variables(self, additional_variables_layers=None, docker_links=None, needed_links=None, needed_services=None):
        # support layered additional_variables: evaluated one at a time on top of the previous resulting environment.
        if additional_variables_layers is None:
            additional_variables_layers = []

        replaced_variables = {}

        # first pass: evaluate env in the context of the source
        if self.has_value():
            for var, value in self.variables.items():
                # destructively remove newlines from environment variables values, as docker doesn't properly support them. It's fine for multiline jsons for example though.
                replaced_variables[var] = common.eval_str_in_env(value, source=self.source).replace('\n', '')

        # second pass: if dependencies also to be started:
        #  add docker_links env_exports
        if common.options.with_dependencies and docker_links is not None:
            # docker_links is a dictionnary of all declared links, we want to export only
            # env_export of linked services
            if needed_links is None:
                raise Exception('You need to define needed_links when using docker_links')
            for link_name in needed_links:
                link = docker_links[link_name]
                for var, value in link.env_exports.items():
                    replaced_variables[var] = value
        #  and needed_services env_exports
        if common.options.with_dependencies and needed_services is not None:
            for needed_service in needed_services:
                for var, value in needed_service.env_exports.items():
                    replaced_variables[var] = value

        # third pass: evaluate additional_variables in the context of second pass env
        for additional_variables in additional_variables_layers:
            if additional_variables is None:
                continue
            previous_layer_env = replaced_variables.copy()
            for var, value in additional_variables.items():
                replaced_variables[var] = common.eval_str_in_env(value, previous_layer_env)

        return replaced_variables

class EnvSerializer(YAML2PipelineSerializer):
    default  = EnvBranchSerializer(optional = True, help_text = "List of environment variables that will be set by default.")
    branches = FieldSerializer('dict', child = EnvBranchSerializer(), default = {}, help_text = "If the branch matches one of the following fields, those variables will be defined as well, eventually replacing the default.", example = {'master': {'ENV_TYPE': 'prod'}})


class SharedVolumes(object):
    volumes = dict()

    allowed_volume_name_pattern = re.compile("^[a-zA-Z0-9][a-zA-Z0-9_.-]+$")

    @staticmethod
    def register(volume, file):
        if volume.name in SharedVolumes.volumes:
            raise DMakeException("Duplicate shared volume named '%s' in '%s'" % (volume.name, file))
        SharedVolumes.volumes[volume.name] = volume

    @staticmethod
    def get(name):
        # search named volume
        volume = SharedVolumes.volumes.get(name, None)
        if volume is None:
            raise SharedVolumeNotFoundException(name)
        return volume

class SharedVolumeSerializer(YAML2PipelineSerializer):
    name = FieldSerializer("string", help_text = "Shared volume name.", example = "datasets")

    def _validate_(self, file, needed_migrations, data, field_name):
        # also accept simple variant where data is a string: the name
        if common.is_string(data):
            data = {'name': data}
        result = super(SharedVolumeSerializer, self)._validate_(file, needed_migrations=needed_migrations, data=data, field_name=field_name)
        if not SharedVolumes.allowed_volume_name_pattern.match(self.name):
            raise ValidationError("Invalid volume name '%s': only '[a-zA-Z0-9][a-zA-Z0-9_.-]+' is allowed. " % (self.name))

        # register volumes globally
        SharedVolumes.register(self, file)
        # unique volume name
        # docker seems to limit around 256, only "[a-zA-Z0-9][a-zA-Z0-9_.-]" are allowed
        self.id = '{repo}.{branch}.{build_id}.{session_id}.{name}'.format(name=self.name, **vars(common))
        return result

    def _serialize_(self, commands, path_dir):
        cmd = "dmake_create_docker_shared_volume %s" % (self.id)
        if common.command == "shell":
            cmd += " 777"
        append_command(commands, 'sh', shell = cmd)

    def get_service_name(self):
        service = self.name + '::shared_volume'  # disambiguate with other services (app services, docker_link services, base services)
        return service

    def get_volume_id(self):
        return self.id


class SharedVolumeMountSerializer(YAML2PipelineSerializer):
    source = FieldSerializer("string", example = "datasets", help_text = "The shared volume name (declared in .")
    target = FieldSerializer("string", example = "/datasets", help_text = "The path in the container where the volume is mounted")

    def _validate_(self, file, needed_migrations, data, field_name):
        # also accept simple variant where data is a string: <volume_name>:<container_path>
        if common.is_string(data):
            parts = data.split(':')
            if len(parts) != 2:
                raise ValidationError("Invalid volume mount: '%s': Volumes shoud be in the form vol_name:/absolute/container/path" % (data))
            data = {'source': parts[0], 'target': parts[1]}

        result = super(SharedVolumeMountSerializer, self)._validate_(file, needed_migrations=needed_migrations, data=data, field_name=field_name)

        if not SharedVolumes.allowed_volume_name_pattern.match(self.source):
            raise ValidationError("Invalid volume mount: source '%s' must be a volume name" % (self.source))

        if self.target[0] not in ['/', '$']:  # later variable expansion can still generate an absolute path
            raise ValidationError("Invalid volume mount: target '%s' must be an absolute path" % (self.target))
        return result

    def get_shared_volume(self):
        return SharedVolumes.get(self.source)

    def get_mount_opt(self, env):
        target = common.eval_str_in_env(self.target, env)

        if target[0] != '/':
            raise DMakeException("Invalid volume mount: `source` '%s', `target` '%s' (expanded from '%s') must be an absolute path" % (self.source, target, self.target))

        volume_id = self.get_shared_volume().get_volume_id()
        options = '-v %s:%s' % (volume_id, target)
        return options

class VolumeMountSerializer(YAML2PipelineSerializer):
    container_volume  = FieldSerializer("string", example = "/mnt", help_text = "Path of the volume mounted in the container")
    host_volume       = FieldSerializer("string", example = "/mnt", help_text = "Path of the volume from the host")

    def _validate_(self, file, needed_migrations, data, field_name):
        # also accept simple variant where data is a string: <host_path>:<container_path>
        if common.is_string(data):
            parts = data.split(':')
            if len(parts) != 2:
                raise ValidationError("Invalid volume mount: '%s': Volumes shoud be in the form /host/path:/absolute/container/path" % (data))
            data = {'host_volume': parts[0], 'container_volume': parts[1]}

        result = super(VolumeMountSerializer, self)._validate_(file, needed_migrations=needed_migrations, data=data, field_name=field_name)

        if self.container_volume[0] != '/':
            raise ValidationError("Invalid volume mount: container_volume '%s' must be an absolute path" % (self.container_volume))
        return result


class DockerBaseSerializer(YAML2PipelineSerializer):
    name                 = FieldSerializer("string", help_text = "Base image name. If no docker user (namespace) is indicated, the image will be kept locally, otherwise it will be pushed.")
    variant              = FieldSerializer("string", optional = True, help_text = "When multiple base_image are defined, this names the base_image variant.", example = "tf")
    root_image           = FieldSerializer("string", optional = True, help_text = "The source image to build on. Defaults to docker.root_image", example = "ubuntu:16.04")
    version              = FieldSerializer("string", help_text = "Deprecated, not used anymore, will be removed later.", default = 'latest')
    install_scripts      = FieldSerializer("array", default = [], child = FieldSerializer("file", executable = True, child_path_only = True), example = ["some/relative/script/to/run"])
    python_requirements  = FieldSerializer("file", default = "", child_path_only = True, help_text = "Path to python requirements.txt.", example = "")
    python3_requirements = FieldSerializer("file", default = "", child_path_only = True, help_text = "Path to python requirements.txt.", example = "requirements.txt")
    copy_files           = FieldSerializer("array", child = FieldSerializer("path", child_path_only = True), default = [], help_text = "Files to copy. Will be copied before scripts are ran. Paths need to be sub-paths to the build file to preserve MD5 sum-checking (which is used to decide if we need to re-build docker base image). A file 'foo/bar' will be copied in '/base/user/foo/bar'.", example = ["some/relative/file/to/copy"])

    def __init__(self, *args, **kwargs):
        self.serializer_version = kwargs.pop('version', 2)
        # Version 2 has mandatory 'variant' and 'root_image'
        if self.serializer_version == 2:
            self.variant.optional = False
            self.root_image.optional = False
        super(DockerBaseSerializer, self).__init__(*args, **kwargs)

    def _serialize_(self, commands, path_dir):
        # Make the temporary directory
        tmp_dir = common.run_shell_command('dmake_make_tmp_dir')

        # Copy file and compute their md5
        files_to_copy = []
        for file in self.copy_files + self.install_scripts:
            files_to_copy.append(file)
        if self.python_requirements:
            files_to_copy.append(self.python_requirements)
        if self.python3_requirements:
            files_to_copy.append(self.python3_requirements)

        # Copy file and keep their md5
        md5s = {}
        for file in files_to_copy:
            md5s[file] = common.run_shell_command('dmake_copy %s %s' % (os.path.join(path_dir, file), os.path.join(tmp_dir, 'user', file)))

        # Set RUN command
        run_cmd = "cd user"
        for file in self.install_scripts:
            run_cmd += " && ./%s" % file

        # Install pip if needed
        if self.python_requirements:
            run_cmd += " && bash ../install_pip.sh && pip install --process-dependency-links -r " + self.python_requirements
        if self.python3_requirements:
            run_cmd += " && bash ../install_pip3.sh && pip3 install --process-dependency-links -r " + self.python3_requirements

        # Save the command in a bash file
        file = 'run_cmd.sh'
        with open(os.path.join(tmp_dir, file), 'w') as f:
            f.write(run_cmd)
        md5s[file] = common.run_shell_command('dmake_md5 %s' % os.path.join(tmp_dir, file))

        # Local environment for templates
        local_env = []
        local_env.append("export ROOT_IMAGE=%s" % self.root_image)
        local_env = ' && '.join(local_env)
        if len(local_env) > 0:
            local_env += ' && '

        # Copy templates
        for file in ["make_base.sh", "config.logrotate", "load_credentials.sh", "install_pip.sh", "install_pip3.sh"]:
            md5s[file] = common.run_shell_command('%s dmake_copy_template docker-base/%s %s' % (local_env, file, os.path.join(tmp_dir, file)))

        # Compute md5 `dmake_digest`
        #  Version 2
        dmake_digest = common.run_shell_command('dmake_md5 %s 2' % (tmp_dir))

        #  Version 1 too for backward compatibility: if version 2 is not found we first check version 1 and tag it as version 2 (it's OK because they are built from the same source: they are equivalent)
        md5_file = os.path.join(tmp_dir, 'md5s')
        with open(md5_file, 'w') as f:
            # sorted for stability
            for md5 in sorted(md5s.items()):
                f.write('%s %s\n' % md5)
        dmake_digest_v1 = common.run_shell_command('dmake_md5 %s' % (md5_file))

        # FIXME: copy key while #493 is not closed: https://github.com/docker/for-mac/issues/483
        if common.key_file is not None:
            common.run_shell_command('cp %s %s' % (common.key_file, os.path.join(tmp_dir, 'key')))

        # Get root_image digest
        try:
            root_image_digest = docker_registry.get_image_digest(self.root_image)
        except requests.exceptions.ConnectionError as e:
            if not common.is_local:
                raise e
            common.logger.warning("""I could not reach the docker registry, you are probably offline.""")
            common.logger.warning("""As a consequence, I cannot check if '{}' is outdated but I will try to continue.""")
            common.logger.warning("""Now trying to find a possibly outdated version of '{}' locally""".format(self.root_image))
            try:
                response = common.run_shell_command('docker image inspect {}'.format(self.root_image))
                root_image_digest = json.loads(response)[0]['RepoDigests'][0].split('@')[1].replace(':', '-')
            except Exception as e:
                common.logger.info('Failed to find {} locally with the following error:'.format(self.root_image))
                raise e

        # Generate base image tag
        self.tag = self._get_base_image_tag(root_image_digest, dmake_digest)
        tag_v1 = self._get_base_image_tag(root_image_digest, dmake_digest_v1, version=1)

        # Never push locally-built base_image from local machines
        push_image = "0" if common.is_local else "1"

        # Append Docker Base build command
        program = 'dmake_build_base_docker'
        args = [tmp_dir,
                self.root_image,
                root_image_digest,
                self.name,
                self.tag,
                tag_v1,
                dmake_digest,
                push_image]
        cmd = '%s %s' % (program, ' '.join(map(common.wrap_cmd, args)))
        append_command(commands, 'sh', shell = cmd)

    @staticmethod
    def _get_base_image_tag(root_image_digest, dmake_digest, version=2):
        dmake_digest_name = 'd2' if version == 2 else 'dd'
        tag = 'base-rid-%s-%s-%s' % (root_image_digest.replace(':', '-'), dmake_digest_name, dmake_digest)
        assert len(tag) <= 128, "docker tag limit"
        return tag

    def get_name_variant(self):
        name_variant = self.name
        if self.variant is not None:
            name_variant += ':' + self.variant
        return name_variant

    def get_service_name(self):
        service = self.get_name_variant() + '::base'  # disambiguate with other services (app services, docker_link services, shared volume services)
        return service

    def get_docker_image(self):
        assert self.tag is not None, "tag must be initialized first"
        image = self.name + ":" + self.tag
        return image

class DockerRootImageSerializer(YAML2PipelineSerializer):
    name = FieldSerializer("string", help_text = "Root image name.", example = "library/ubuntu")
    tag  = FieldSerializer("string", help_text = "Root image tag (you can use environment variables).", example = "16.04")

class DockerSerializer(YAML2PipelineSerializer):
    root_image   = FieldSerializer([FieldSerializer("file", help_text = "to another dmake file, in which base the root_image will be this file's base_image."), DockerRootImageSerializer()], optional = True, help_text = "The default source image name to build on.")
    base_image   = FieldSerializer([DockerBaseSerializer(version = 1), "array"], child = DockerBaseSerializer(version = 2), default = [], help_text = "Base (development environment) imags.")
    mount_point  = FieldSerializer("string", default = "/app", help_text = "Mount point of the app in the built docker image. Needs to be an absolute path.")
    command      = FieldSerializer("string", default = "bash", help_text = "Only used when running 'dmake shell': command passed to `docker run`")

    def _validate_(self, file, needed_migrations, data, field_name):
        super(DockerSerializer, self)._validate_(file, needed_migrations=needed_migrations, data=data, field_name=field_name)

        # make base_image an array
        base_image = self.base_image
        self.__fields__['base_image'].value = [base_image] if isinstance(base_image, DockerBaseSerializer) else base_image

        # check variant duplicates
        seen = set()
        for base_image in self.base_image:
            variant = base_image.variant
            if variant not in seen:
                seen.add(variant)
            else:
                raise DMakeException("`base_image` '%s': duplicate variant: '%s' (file: '%s')" % (base_image.name, variant, file))

        return self

    def get_base_image(self, variant=None, fallback_to_root_image=True):
        # default base_image: the first one
        if variant is None:
            if len(self.base_image) > 0:
                return self.base_image[0]
            else:
                return None
        # explicit variant
        for base_image in self.base_image:
            if base_image.variant == variant:
                return base_image
        # variant not found
        raise DMakeException("Unknown base_image variant '%s'" % variant)

    def get_docker_base_image(self, variant=None):
        base_image = self.get_base_image(variant=variant)
        if base_image is None:
            return self.root_image
        else:
            return base_image.get_docker_image()

    def get_base_image_from_service_name(self, base_image_service_name):
        for base_image in self.base_image:
            if base_image.get_service_name() == base_image_service_name:
                return base_image
        raise DMakeException("Could not find base_image service '%s'" % base_image_service_name)

class HTMLReportSerializer(YAML2PipelineSerializer):
    directory  = FieldSerializer("string", example = "test-reports/cover", help_text = "Directory of the html pages.")
    index      = FieldSerializer("string", default = "index.html", help_text = "Main page.")
    title      = FieldSerializer("string", default = "HTML Report", help_text = "Main page title.")

class DockerLinkSerializer(YAML2PipelineSerializer):
    image_name       = FieldSerializer("string", example = "mongo:3.2", help_text = "Name and tag of the image to launch.")
    link_name        = FieldSerializer("string", example = "mongo", help_text = "Link name.")
    volumes          = FieldSerializer("array", child = FieldSerializer([SharedVolumeMountSerializer(), VolumeMountSerializer()]), default = [], example = ["datasets:/datasets", "/mnt:/mnt"], help_text = "Either shared volumes to mount. Or: for the 'shell' command only. The list of volumes to mount on the link. It must be in the form ./host/path:/absolute/container/path. Host path is relative to the dmake file.")
    need_gpu         = FieldSerializer("bool", default = False, help_text = "Whether the docker link needs to be run on a GPU node.")
    # TODO: This field is badly named. Link are used by the run command also, nothing to do with testing or not. It should rather be: 'docker_options'
    testing_options  = FieldSerializer("string", default = "", example = "-v /mnt:/data", help_text = "Additional Docker options when testing on Jenkins.")
    probe_ports      = FieldSerializer(["string", "array"], default = "auto", child = "string", help_text = "Either 'none', 'auto' or a list of ports in the form 1234/tcp or 1234/udp")
    env              = FieldSerializer("dict", child = "string", default = {}, example = {'REDIS_URL': '${REDIS_URL}'}, help_text = "Additional environment variables defined when running this image.")
    env_exports      = FieldSerializer("dict", child = "string", default = {}, help_text = "A set of environment variables that will be exported in services that use this link when testing.")

    def get_options(self, path, env):
        options = common.eval_str_in_env(self.testing_options, env)
        in_shell = common.command == "shell"
        for volume in self.volumes:
            if isinstance(volume, SharedVolumeMountSerializer):
                # named shared volume
                options += ' ' + volume.get_mount_opt(env)
            elif isinstance(volume, VolumeMountSerializer):
                if not in_shell:
                    # skip host vols in non shell (i.e. in test: we don't want persistence)
                    continue
                host_vol = common.eval_str_in_env(volume.host_volume, env)

                # late validation (cannot do it before variable substitution which requires `env`: cannot be done before now)
                if host_vol[0] not in ['/', '.']:
                    raise DMakeException("Invalid volume mount: '%s' (from source: '%s'): host_volume must be an absolute or relative path in the host." % (host_vol, volume.host_volume))

                # Turn it into an absolute path
                if host_vol[0] == '.':
                    host_vol = os.path.normpath(os.path.join(common.root_dir, path, host_vol))
                options += ' -v %s:%s' % (host_vol, volume.container_volume)
            else:
                assert False, "Unknown DockerLink volume type"
        return options

    def get_env(self, context_env):
        env = {}
        for key, value in self.env.items():
            env[key] = common.eval_str_in_env(value, context_env)
        return env

    def get_shared_volumes(self):
        return [volume.get_shared_volume() for volume in self.volumes if isinstance(volume, SharedVolumeMountSerializer)]

    def probe_ports_list(self):
        if isinstance(self.probe_ports, list):
            good = True
            for p in self.probe_ports:
                i = p.find('/')
                port = p[:i]
                proto = p[(i + 1):]
                if proto not in ['udp', 'tcp']:
                    good = False
                    break
                if proto == 'udp':
                    raise DMakeException("TODO: udp support in dmake_wait_for_it")
                try:
                    if int(port) < 0:
                        good = False
                        break
                except:
                    good = False
                    break

            if good:
                return ','.join(self.probe_ports)
        elif self.probe_ports in ['auto', 'none']:
            return self.probe_ports

        raise DMakeException("Badly formatted probe ports.")

    def get_docker_run_gpu_cmd_prefix(self):
        return get_docker_run_gpu_cmd_prefix(self.need_gpu, 'docker link', self.link_name)

class AWSBeanStalkDeploySerializer(YAML2PipelineSerializer):
    name_prefix  = FieldSerializer("string", default = "${DMAKE_DEPLOY_PREFIX}", help_text = "The prefix to add to the 'deploy_name'. Can be useful as application name have to be unique across all users of Elastic BeanStalk.")
    region       = FieldSerializer("string", default = "eu-west-1", help_text = "The AWS region where to deploy.")
    stack        = FieldSerializer("string", default = "64bit Amazon Linux 2016.03 v2.1.6 running Docker 1.11.2")
    options      = FieldSerializer("file", example = "path/to/options.txt", help_text = "AWS Option file as described here: http://docs.aws.amazon.com/elasticbeanstalk/latest/dg/command-options-general.html")
    credentials  = FieldSerializer("string", optional = True, help_text = "S3 path to the credential file to authenticate a private docker repository.")
    ebextensions = FieldSerializer("dir", optional = True, help_text = "Path to the ebextension directory. See http://docs.aws.amazon.com/elasticbeanstalk/latest/dg/ebextensions.html")

    def _serialize_(self, commands, app_name, deploy_name, config, image_name, env):
        if not self.has_value():
            return

        tmp_dir = common.run_shell_command('dmake_make_tmp_dir')

        for port in config.ports:
            if port.container_port != port.host_port:
                raise DMakeException("AWS Elastic Beanstalk only supports ports binding which are the same in the container and the host.")
        ports = [{"ContainerPort": ports.container_port} for ports in config.ports]
        volumes = [
            {
                "HostDirectory": volume.host_volume,
                "ContainerDirectory": volume.container_volume
            } for volume in config.volumes if volume.host_volume != "/var/log/deepomatic" # Cannot specify a volume both in logging and mounting
        ]

        if config.readiness_probe.get_cmd() != "":
            raise DMakeException("Readiness probe for AWS is not supported yet.")
        if len(config.docker_opts) > 0:
            raise DMakeException("Docker options for AWS is not supported yet.")

        # Default Dockerrun.aws.json
        data = {
            "AWSEBDockerrunVersion": "1",
            "Image": {
                "Name": image_name,
                "Update": "true"
            },
            "Ports": ports,
            "Volumes": volumes,
            "Logging": "/var/log/deepomatic"
        }

        # Generate Dockerrun.aws.json
        if self.credentials is not None:
            if self.credentials.startswith('s3://'):
                credentials = self.credentials[len('s3://'):]
            else:
                raise DMakeException("Credentials should start with 's3://'")

            credentials = credentials.split('/')
            key = '/'.join(credentials[1:])
            bucket = credentials[0]

            data["Authentication"] = {
                "Bucket": bucket,
                "Key": key
            }

        with open(os.path.join(tmp_dir, "Dockerrun.aws.json"), 'w') as dockerrun:
            json.dump(data, dockerrun)

        option_file = os.path.join(tmp_dir, 'options.txt')
        common.run_shell_command('dmake_replace_vars %s %s' % (self.options, option_file), additional_env=env)
        with open(option_file, 'r') as f:
            options = json.load(f)
        for var, value in env.items():
            found = False
            for opt in options:
                if opt['OptionName'] == var:
                    found = True
                    break
            if not found:
                options.append({
                    "Namespace": "aws:elasticbeanstalk:application:environment",
                    "OptionName": var,
                    "Value": value
                })
        with open(option_file, 'w') as f:
            json.dump(options, f)

        if self.ebextensions is not None:
            common.run_shell_command('cp -LR %s %s' % (self.ebextensions, os.path.join(tmp_dir, ".ebextensions")))

        deploy_name = common.eval_str_in_env(self.name_prefix, env) + deploy_name
        append_command(commands, 'sh', shell = 'dmake_deploy_aws_eb "%s" "%s" "%s" "%s"' % (
            tmp_dir,
            deploy_name,
            self.region,
            self.stack))

class SSHDeploySerializer(YAML2PipelineSerializer):
    user = FieldSerializer("string", example = "ubuntu", help_text = "User name")
    host = FieldSerializer("string", example = "192.168.0.1", help_text = "Host address")
    port = FieldSerializer("int", default = 22, help_text = "SSH port")

    def _serialize_(self, commands, app_name, deploy_name, config, image_name, env):
        if not self.has_value():
            return

        tmp_dir = common.run_shell_command('dmake_make_tmp_dir')
        deploy_name = deploy_name + "-%s" % common.branch.lower()
        env_file = generate_env_file(tmp_dir, env)

        opts = config.full_docker_opts(env, mount_host_volumes=True) + " --env-file " + os.path.basename(env_file)

        # TODO: find a proper way to login on docker when deploying via SSH
        common.run_shell_command('cp -R ${HOME}/.docker* %s/ || :' % tmp_dir)

        start_file = os.path.join(tmp_dir, "start_app.sh")
        # Deprecated: ('export LAUNCH_LINK="%s" && ' % launch_links) + \
        cmd = ('export IMAGE_NAME="%s" && ' % image_name) + \
              ('export APP_NAME="%s" && ' % deploy_name) + \
              ('export DOCKER_OPTS="%s" && ' % opts) + \
              ('export READYNESS_PROBE="%s" && ' % common.escape_cmd(config.readiness_probe.get_cmd())) + \
              ('export DOCKER_CMD="%s" && ' % ('nvidia-docker' if config.need_gpu else 'docker')) + \
               'dmake_copy_template deploy/deploy_ssh/start_app.sh %s' % start_file
        common.run_shell_command(cmd)

        cmd = 'dmake_deploy_ssh "%s" "%s" "%s" "%s" "%d"' % (tmp_dir, deploy_name, self.user, self.host, self.port)
        append_command(commands, 'sh', shell = cmd)

class K8SCDDeploySerializer(YAML2PipelineSerializer):
    context   = FieldSerializer("string", help_text = "kubectl context to use.")
    namespace = FieldSerializer("string", default = "default", help_text = "Kubernetes namespace to target")
    selectors = FieldSerializer("dict", default = {}, child = "string", help_text = "Selectors to restrict the deployment.")

    def _serialize_(self, commands, app_name, deploy_name, image_name, env):
        if not self.has_value():
            return

        selectors = []
        for key, value in self.selectors.items():
            if value.find(','):
                raise DMakeException("Cannot have ',' in selector value")
            selectors.append("%s=%s" % (key, value))
        selectors = ",".join(selectors)

        tmp_dir = common.run_shell_command('dmake_make_tmp_dir')
        configmap_env_file = os.path.join(tmp_dir, 'kubernetes-configmap-env.yaml')
        configmap_env_labels = {
            'app': deploy_name,
            'product': app_name
        }
        k8s_utils.generate_config_map_file(env, deploy_name, configmap_env_file, labels=configmap_env_labels)

        program = 'dmake_deploy_k8s_cd'
        args = [common.tmp_dir,
                common.eval_str_in_env(self.context, env),
                common.eval_str_in_env(self.namespace, env),
                app_name,
                deploy_name,
                image_name,
                configmap_env_file,
                selectors]
        cmd = '%s %s' % (program, ' '.join(map(common.wrap_cmd, args)))
        append_command(commands, 'sh', shell = cmd)


class KubernetesConfigMapFromFileSerializer(YAML2PipelineSerializer):
    key  = FieldSerializer("string", example="nginx.conf", help_text="File key")
    path = FieldSerializer("file",  example="deploy/nginx.conf", help_text="File path (relative to this dmake.yml file)")

    def get_arg(self):
        arg = "--from-file=%s=%s" % (self.key, self.path)
        return arg


class KubernetesSecretFromFileSerializer(YAML2PipelineSerializer):
    key  = FieldSerializer("string", example="ssh-privatekey", help_text="File key")
    path = FieldSerializer("string",  example="${SECRETS}/ssh_id_rsa", help_text="Absolute file path. Supports variables substitution.")

    def get_arg(self, env):
        path = common.eval_str_in_env(self.path, env)

        if not os.path.isfile(path):
            raise DMakeException("Invalid Kubernetes Secret 'from_files' absolute path: key '%s', path '%s' (expanded from '%s'): file not found" % (self.key, path, self.path))

        arg = "--from-file=%s=%s" % (self.key, path)
        return arg


class KubernetesConfigMapSerializer(YAML2PipelineSerializer):
    name       = FieldSerializer("string", example="nginx", help_text="Kubernetes ConfigMap name")
    from_files = FieldSerializer("array", child=KubernetesConfigMapFromFileSerializer(), default=[], help_text="Kubernetes create values from files")

    def generate_manifest(self, env, labels):
        from_file_args = [file_source.get_arg() for file_source in self.from_files]
        data_str = k8s_utils.generate_from_create(args=['configmap'], name=self.name, from_file_args=from_file_args)
        return k8s_utils.dump_all_str_and_add_labels(data_str, labels=labels)



class KubernetesSecretGenericSerializer(YAML2PipelineSerializer):
    from_files = FieldSerializer("array", child=KubernetesSecretFromFileSerializer(), default=[], help_text="Kubernetes create values from files")


class KubernetesSecretSerializer(YAML2PipelineSerializer):
    name    = FieldSerializer("string", example="ssh-key", help_text="Kubernetes Secret name")
    generic = FieldSerializer(KubernetesSecretGenericSerializer(), help_text="Kubernetes Generic Secret type parameters")

    def generate_manifest(self, env, labels):
        from_file_args = [file_source.get_arg(env) for file_source in self.generic.from_files]
        data_str = k8s_utils.generate_from_create(args=['secret', 'generic'], name=self.name, from_file_args=from_file_args)
        return k8s_utils.dump_all_str_and_add_labels(data_str, labels=labels)


class KubernetesManifestSerializer(YAML2PipelineSerializer):
    template  = FieldSerializer("file", example="path/to/kubernetes-manifest.yaml", help_text="Kubernetes manifest file (Python PEP 292 template format) defining all the resources needed to deploy the service")
    variables = FieldSerializer('dict', child="string", default={}, help_text="Defines variables used in the kubernetes manifest template", example={'TLS_SECRET_NAME': '${K8S_DEPLOY_TLS_SECRET_NAME}'})

    def _validate_(self, file, needed_migrations, data, field_name):
        # also accept simple variant where data is a string: file path to the kubernetes manifest template
        if common.is_string(data):
            data = {'template': data}

        result = super(KubernetesManifestSerializer, self)._validate_(file, needed_migrations=needed_migrations, data=data, field_name=field_name)
        return result

    def get_template_variables(self, env):
        replaced_variables = {}

        for var, value in self.variables.items():
            replaced_variables[var] = common.eval_str_in_env(value, env, strict = True)

        return replaced_variables


class KubernetesDeploySerializer(YAML2PipelineSerializer):
    context     = FieldSerializer("string", help_text="kubectl context to use.")
    namespace   = FieldSerializer("string", optional=True, help_text="Kubernetes namespace to target (overrides kubectl context default namespace")
    manifest    = FieldSerializer(KubernetesManifestSerializer(), optional=True, help_text="Kubernetes manifest defining all the resources needed to deploy the service")
    config_maps = FieldSerializer("array", child=KubernetesConfigMapSerializer(), default=[], help_text="Additional Kubernetes ConfigMaps")
    secrets     = FieldSerializer("array", child=KubernetesSecretSerializer(), default=[], help_text="Additional Kubernetes Secrets")

    def _serialize_(self, commands, app_name, deploy_name, image_name, env):
        if not self.has_value():
            return

        tmp_dir = common.run_shell_command('dmake_make_tmp_dir')

        # dmake service label used for pruning resources on kubectl apply: dmake automatically adds this label to all (top level) resources, then kubectl apply is limited to these resources by label selection
        dmake_generated_labels = {
            'dmake.deepomatic.com/service': deploy_name
        }
        extra_labels = {
            'app': deploy_name,
            'product': app_name
        }
        manifest_files = []

        # generate ConfigMap containing runtime environment variables
        configmap_env_filename = 'kubernetes-configmap-env.yaml'
        manifest_files.append('no-pruning:%s' % (configmap_env_filename))
        configmap_env_labels = dmake_generated_labels.copy()
        configmap_env_labels.update({
            'dmake.deepomatic.com/prune': 'no-pruning'
        })
        configmap_env_labels.update(extra_labels)
        configmap_name = k8s_utils.generate_config_map_file(env, deploy_name, os.path.join(tmp_dir, configmap_env_filename), labels = configmap_env_labels)

        # additional resources
        def generate_and_write_additional_resources(sources, filename):
            if not sources:
                return
            manifest_files.append(filename)
            data = [source.generate_manifest(env=env, labels=extra_labels) for source in sources]
            # concat manifests
            data_str = '%s\n' % ('\n\n---\n\n'.join(data))
            # write manifests to file
            with open(os.path.join(tmp_dir, filename), 'w') as f:
                k8s_utils.dump_all_str_and_add_labels(data_str, dmake_generated_labels, f)

        user_configmaps_filename = 'kubernetes-user-configmaps.yaml'
        generate_and_write_additional_resources(self.config_maps, user_configmaps_filename)
        user_secrets_filename = 'kubernetes-user-secrets.yaml'
        generate_and_write_additional_resources(self.secrets, user_secrets_filename)

        # copy/render template manifest file
        context = common.eval_str_in_env(self.context, env)
        namespace = common.eval_str_in_env(self.namespace, env) if self.namespace else ""
        if self.manifest is not None:
            user_manifest_filename = 'kubernetes-user-manifest.yaml'
            manifest_files.append(user_manifest_filename)
            user_manifest_path = os.path.join(tmp_dir, user_manifest_filename)
            change_cause = "DMake deploy %s from repo %s#%s (%s)" % (deploy_name, common.repo, common.branch, common.commit_id)
            template_default_context = {
                'SERVICE_NAME': deploy_name,
                'CHANGE_CAUSE': change_cause,
                'DOCKER_IMAGE_NAME': image_name,
                'CONFIGMAP_ENV_NAME': configmap_name
            }
            template_context = self.manifest.get_template_variables(env)
            template_context.update(template_default_context)
            with open(self.manifest.template, 'r') as f:
                user_manifest_template = Template(f.read())
            user_manifest_data_str = user_manifest_template.substitute(**template_context)
            with open(user_manifest_path, 'w') as f:
                k8s_utils.dump_all_str_and_add_labels(user_manifest_data_str, dmake_generated_labels, f)
            # verify the manifest file
            program = 'kubectl'
            args = ['--context=%s' % context, 'apply', '--dry-run=true', '--validate=true', '--filename=%s' % user_manifest_path]
            cmd = '%s %s' % (program, ' '.join(map(common.wrap_cmd, args)))
            try:
                common.run_shell_command(cmd, raise_on_return_code=True)
            except common.ShellError as e:
                raise DMakeException("%s: Invalid Kubernetes manifest file %s (rendered template: %s): %s" % (deploy_name, self.manifest.template, user_manifest_path, e))

        # generate call to kubernetes
        program = 'dmake_deploy_kubernetes'
        args = [tmp_dir,
                context,
                namespace,
                deploy_name,
                common.repo,
                common.branch,
                common.commit_id]
        args += manifest_files
        cmd = '%s %s' % (program, ' '.join(map(common.wrap_cmd, args)))
        append_command(commands, 'sh', shell = cmd)


class DeployConfigPortsSerializer(YAML2PipelineSerializer):
    container_port    = FieldSerializer("int", example = 8000, help_text = "Port on the container")
    host_port         = FieldSerializer("int", optional = True, example = 80, help_text = "Port on the host. If not set, a random port will be used.")

class DeployStageSerializer(YAML2PipelineSerializer):
    description   = FieldSerializer("string", example = "Deployment on AWS and via SSH", help_text = "Deploy stage description.")
    branches      = FieldSerializer(["string", "array"], child = "string", default = ['stag'], post_validation = lambda x: [x] if common.is_string(x) else x, help_text = "Branch list for which this stag is active, '*' can be used to match any branch. Can also be a simple string.")
    env           = FieldSerializer("dict", child = "string", default = {}, example = {'AWS_ACCESS_KEY_ID': '1234', 'AWS_SECRET_ACCESS_KEY': 'abcd'}, help_text = "Additionnal environment variables for deployment.")
    aws_beanstalk = AWSBeanStalkDeploySerializer(optional = True, help_text = "Deploy via Elastic Beanstalk")
    ssh           = SSHDeploySerializer(optional = True, help_text = "Deploy via SSH")
    k8s_continuous_deployment = K8SCDDeploySerializer(optional = True, help_text = "Continuous deployment via Kubernetes. Look for all the deployments running this service.")
    kubernetes    = KubernetesDeploySerializer(optional = True, help_text = "Deploy to Kubernetes cluster.")

class ServiceDockerCommonSerializer(YAML2PipelineSerializer):
    name             = FieldSerializer("string", optional = True, help_text = "Name of the docker image to build. By default it will be {:app_name}-{:service_name}. If there is no docker user, it won be pushed to the registry. You can use environment variables.")
    base_image_variant = FieldSerializer(["string", "array"], optional = True, child = "string", help_text = "Specify which `base_image` variants are used as `base_image` for this service. Array: multi-variant service. Default: first 'docker.base_image'.")
    check_private    = FieldSerializer("bool",   default = True,  help_text = "Check that the docker repository is private before pushing the image.")
    tag              = FieldSerializer("string", optional = True, help_text = "Tag of the docker image to build. By default it will be '[{:variant}-]{:branch_name}-{:build_id}'")

    def set_service(self, service):
        self.service = service

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
            tag = common.branch.lower()
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

    def is_runnable(self):
        return self._is_runnable()

    def _is_runnable(self):
        # pure virtual method, implemented in children classes
        raise NotImplementedError()

    def generate_build_docker(self, commands, path_dir, docker_base, build):
        self._generate_build_docker(commands, path_dir, docker_base, build)

    def _generate_build_docker(self, commands, path_dir, docker_base, build):
        # pure virtual method, implemented in children classes
        raise NotImplementedError()

class ServiceDockerV1Serializer(ServiceDockerCommonSerializer):
    # v1: dmake generated Dockerfile
    workdir          = FieldSerializer("dir",    optional = True, help_text = "Working directory of the produced docker file, must be an existing directory. By default it will be directory of the dmake file.")
    copy_directories = FieldSerializer("array", child = "dir", default = [], help_text = "Directories to copy in the docker image.")
    install_script   = FieldSerializer("file", child_path_only = True, executable = True, optional = True, example = "install.sh", help_text = "The install script (will be run in the docker). It has to be executable.")
    entrypoint       = FieldSerializer("file", child_path_only = True, executable = True, optional = True, help_text = "Set the entrypoint of the docker image generated to run the app.")
    start_script     = FieldSerializer("file", child_path_only = True, executable = True, optional = True, example = "start.sh", help_text = "The start script (will be run in the docker). It has to be executable.")

    def _is_runnable(self):
        return self.start_script is not None

    def _generate_build_docker(self, commands, path_dir, docker_base, build):
        tmp_dir = common.run_shell_command('dmake_make_tmp_dir')
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

        image_name = self.get_image_name()
        append_command(commands, 'sh', shell = 'dmake_build_docker "%s" "%s"' % (tmp_dir, image_name))

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

class ServiceDockerV2Serializer(ServiceDockerCommonSerializer):
    # v2: user provided Dockerfile
    build            = ServiceDockerBuildSerializer(help_text = "Docker build options for service built using user-provided Dockerfile (ignore `.build.commands`), like in Docker Compose files.`")

    def _is_runnable(self):
        # assume the user-provided Dockerfile is a runnable service
        return True

    def _generate_build_docker(self, commands, path_dir, docker_base, build):
        image_name = self.get_image_name()
        base_image_name = docker_base.get_docker_base_image(self.base_image_variant)
        build_args = {
            'BASE_IMAGE': base_image_name,
            'WORKDIR': os.path.join(docker_base.mount_point, path_dir),
        }
        self.build._serialize_(commands, path_dir, image_name, build_args)

class ReadinessProbeSerializer(YAML2PipelineSerializer):
    command               = FieldSerializer("array", child = "string", default = [], example = ['cat', '/tmp/worker_ready'], help_text = "The command to run to check if the container is ready. The command should fail with a non-zero code if not ready.")
    initial_delay_seconds = FieldSerializer("int", default = 0, example = 1, help_text = "The delay before the first probe is launched")
    period_seconds        = FieldSerializer("int", default = 5, example = 5, help_text = "The delay between two first probes")
    max_seconds           = FieldSerializer("int", default = 0, example = 40, help_text = "The maximum delay after failure")

    def get_cmd(self):
        if not self.has_value() or len(self.command) == 0:
            return ""

        if self.max_seconds > 0:
            condition = "$T -le %d" % self.max_seconds
        else:
            condition = "1"

        period = max(self.period_seconds, 1)

        # Make the command with "" around parameters
        cmd = self.command[0] + ' ' + (' '.join([common.wrap_cmd(c) for c in self.command[1:]]))
        cmd = """T=0; sleep {initial_delay:d}; while [ {condition} ]; do echo "Running readiness probe"; {cmd}; if [ "$?" = "0" ]; then echo "... ready"; exit 0; fi; T=$((T+{period:d})); sleep {period:d}; done; exit 1;""".format(initial_delay=self.initial_delay_seconds, condition=condition, cmd=cmd, period=period)
        cmd = common.escape_cmd(cmd)
        return 'bash -c "%s"' % cmd

class DeployConfigSerializer(YAML2PipelineSerializer):
    docker_image       = FieldSerializer([ServiceDockerV1Serializer(), ServiceDockerV2Serializer()], allow_null = True, help_text = "Docker to build for running and deploying.")
    docker_opts        = FieldSerializer("string", default = "", example = "--privileged", help_text = "Docker options to add.")
    env_override       = FieldSerializer("dict", child = "string", optional = True, default = {}, help_text = "Extra environment variables for this service. Overrides dmake.yml root `env`, with variable substitution evaluated from it.", example = {'INFO': '${BRANCH}-${BUILD}'})
    need_gpu           = FieldSerializer("bool", default = False, help_text = "Whether the service needs to be run on a GPU node.")
    ports              = FieldSerializer("array", child = DeployConfigPortsSerializer(), default = [], help_text = "Ports to open.")
    volumes            = FieldSerializer("array", child = FieldSerializer([SharedVolumeMountSerializer(), VolumeMountSerializer()]), default = [], example = ["datasets:/datasets"], help_text = "Volumes to mount.")
    readiness_probe    = ReadinessProbeSerializer(optional = True, help_text = "A probe that waits until the container is ready.")

    def full_docker_opts(self, env, mount_host_volumes, use_host_ports=None):
        if not self.has_value():
            return ""

        if use_host_ports is None:
            # None means do it if user asked it via global config
            use_host_ports = common.use_host_ports
        opts = []
        for ports in self.ports:
            if not use_host_ports or ports.host_port is None:
                opts.append("-p %d" % ports.container_port)
            else:
                opts.append("-p 0.0.0.0:%d:%d" % (ports.host_port, ports.container_port))

        for volume in self.volumes:
            if isinstance(volume, SharedVolumeMountSerializer):
                # named shared volume
                if mount_host_volumes:
                    raise DMakeException("Named shared volume not supported by ssh deployment: '%s'" % (volume))
                opts.append(volume.get_mount_opt(env))
                continue

            # else: VolumeMountSerializer
            assert isinstance(volume, VolumeMountSerializer), "Unknown DeployConfig volume type"
            if not mount_host_volumes:
                # fake mount: mount to a dmake-local directory
                host_volume = os.path.join(common.cache_dir, 'volumes', volume.host_volume)
                try:
                    os.mkdir(host_volume)
                except OSError:
                    pass
            else:
                host_volume = volume.host_volume

            # On MacOs, the /var directory is actually in /private
            # So you have to activate /private/var in the shard directories
            if common.uname == "Darwin" and host_volume.startswith('/var/'):
                host_volume = '/private/' + host_volume

            opts.append("-v %s:%s" % (common.join_without_slash(host_volume), common.join_without_slash(volume.container_volume)))

        docker_opts = self.docker_opts
        if not common.is_local:
            docker_opts = docker_opts.replace('--privileged', '')
        opts = docker_opts + " " + (" ".join(opts))
        return opts

class DeploySerializer(YAML2PipelineSerializer):
    deploy_name = FieldSerializer("string", optional = True, example = "", help_text = "The name used for deployment. Will default to '{:app_name}-{:service_name}' if not specified")
    stages      = FieldSerializer("array", child = DeployStageSerializer(), help_text = "Deployment possibilities")

    def set_service(self, service):
        self.service = service

    def generate_deploy(self, commands, app_name, env, config):
        deploy_env = env.get_replaced_variables(additional_variables_layers=[self.service.config.env_override])
        if self.deploy_name is not None:
            deploy_name = common.eval_str_in_env(self.deploy_name, deploy_env)
        else:
            deploy_name = "%s-%s" % (app_name, self.service.original_service_name)
        if self.service.is_variant:
            deploy_name += "-%s" % self.service.variant

        image_name = config.docker_image.get_image_name(env = deploy_env)
        # When deploying, we need to push the image. We make sure that the image has a user
        if len(image_name.split('/')) == 1:
            image_name_without_tag = image_name.split(':')[0]
            raise DMakeException("Service '{}' declares a docker image without a user name in config::docker_image::name so I cannot deploy it. I suggest to change it to 'your_company/{}'".format(self.service.service_name, image_name_without_tag))
        append_command(commands, 'sh', shell = 'dmake_push_docker_image "%s" "%s"' % (image_name, "1" if config.docker_image.check_private else "0"))
        image_latest = config.docker_image.get_image_name(env = deploy_env, latest = True)
        append_command(commands, 'sh', shell = 'docker tag %s %s && dmake_push_docker_image "%s" "%s"' % (image_name, image_latest, image_latest, "1" if config.docker_image.check_private else "0"))

        for stage in self.stages:
            branches = stage.branches
            if common.branch not in branches and '*' not in branches:
                continue

            branch_env = env.get_replaced_variables(additional_variables_layers=[self.service.config.env_override, stage.env])
            stage.aws_beanstalk._serialize_(commands, app_name, deploy_name, config, image_name, branch_env)
            stage.ssh._serialize_(commands, app_name, deploy_name, config, image_name, branch_env)
            stage.k8s_continuous_deployment._serialize_(commands, app_name, deploy_name, image_name, branch_env)
            stage.kubernetes._serialize_(commands, app_name, deploy_name, image_name, branch_env)

class DataVolumeSerializer(YAML2PipelineSerializer):
    container_volume  = FieldSerializer("string", example = "/mnt", help_text = "Path of the volume mounted in the container")
    source            = FieldSerializer("string", example = "s3://my-bucket/some/folder", help_text = "Only host path and s3 URLs are supported for now.")
    read_only         = FieldSerializer("bool",   default = False,  help_text = "Flag to set the volume as read-only")

    def get_mount_opt(self, service_name, dmake_file_path, env=None):
        if env is None:
            env = {}

        scheme = None
        path = ""

        source = common.eval_str_in_env(self.source, env)
        container_volume = common.eval_str_in_env(self.container_volume, env)

        if source[0:1] in ['/', '.']:
            scheme = 'file'
            path = source
        else:
            i = source.find('://')
            if i >= 0:
                scheme = source[:i]
                path = source[(i + 3):]

        if scheme == "file":
            # Turn it into an absolute path
            if path[0:1] == '.':
                path = os.path.normpath(os.path.join(common.root_dir, dmake_file_path, path))
        elif scheme == "s3":
            path = os.path.join(common.config_dir, 'data_volumes', 's3', service_name.replace(':', '-'), path)
            common.run_shell_command('aws s3 sync %s %s' % (source, path))
        else:
            raise DMakeException("Invalid data volume mount: Field `source` '%s' (expanded from '%s') must be a host path or start with 's3://'" % (source, self.source))

        options = '-v %s:%s' % (path, container_volume)
        if self.read_only:
            options += ':ro'
        return options


class TestSerializer(YAML2PipelineSerializer):
    docker_links_names = FieldSerializer(deprecated="Use 'services:needed_links' instead", data_type="array", child = "string", migration='0001_docker_links_names_to_needed_links', default = [], example = ['mongo'], help_text = "The docker links names to bind to for this test. Must be declared at the root level of some dmake file of the app.")
    data_volumes       = FieldSerializer("array", child = DataVolumeSerializer(), default = [], help_text = "The read only data volumes to mount. Only S3 is supported for now.")
    commands           = FieldSerializer("array", child = "string", example = ["python manage.py test"], help_text = "The commands to run for integration tests.")
    timeout            = FieldSerializer("string", optional = True, example = "600", help_text = "The timeout (in seconds) to apply to the tests execution (excluding dependencies, setup, and potential resources locks).")
    junit_report       = FieldSerializer(["string", "array"], child = "string", default = [], post_validation = lambda x: [x] if common.is_string(x) else x, example = "test-reports/nosetests.xml", help_text = "Filepath or array of file paths of xml xunit test reports. Publish a XUnit test report.")
    cobertura_report   = FieldSerializer(["string", "array"], child = "string", default = [], post_validation = lambda x: [x] if common.is_string(x) else x, example = "test-reports/coverage.xml", help_text = "Filepath or array of file paths of xml xunit test reports. Publish a Cobertura report.")
    html_report        = HTMLReportSerializer(optional = True, help_text = "Publish an HTML report.")

    def get_mounts_opt(self, service_name, path, env):
        if not self.has_value():
            return ''
        opts = []
        for data_volume in self.data_volumes:
            opts.append(data_volume.get_mount_opt(service_name, path, env))
        return ' ' + ' '.join(opts)

    def generate_test(self, commands, path, service_name, docker_cmd, docker_links, mount_point):
        if not self.has_value() or len(self.commands) == 0:
            return

        tests_cmd = '/bin/bash -c %s' % common.wrap_cmd_simple_quotes(' && '.join(self.commands))

        has_timeout = self.timeout is not None
        if has_timeout:
            append_command(commands, 'timeout', time = self.timeout)

        append_command(commands, 'sh', shell = docker_cmd + tests_cmd)

        if has_timeout:
            append_command(commands, 'timeout_end')

        for junit_report in self.junit_report:
            append_command(commands, 'junit', report = os.path.join(path, junit_report), service_name = service_name, mount_point = mount_point)

        for cobertura_report in self.cobertura_report:
            append_command(commands, 'cobertura', report = os.path.join(path, cobertura_report), service_name = service_name, mount_point = mount_point)

        html = self.html_report._value_()
        if html is not None:
            append_command(commands, 'publishHTML', service_name = service_name, mount_point = mount_point,
                           directory = os.path.join(path, html['directory']),
                           index     = html['index'],
                           title     = html['title'],)


allowed_link_name_pattern = re.compile("^[a-z0-9-]{1,63}$")  # too laxist, but easy to read
class NeededServiceSerializer(YAML2PipelineSerializer):
    service_name    = FieldSerializer("string", help_text = "The name of the needed application part.", example = "worker-nn", no_slash_no_space = True)
    link_name       = FieldSerializer("string", optional = True, example = "worker-nn", help_text = "Link name.")
    env             = FieldSerializer("dict", child = "string", optional = True, default = {}, help_text = "List of environment variables that will be set when executing the needed service.", example = {'CNN_ID': '2'})
    env_exports     = FieldSerializer("dict", child = "string", default = {}, help_text = "A set of environment variables that will be exported in services that use this service when testing.")

    def __init__(self, **kwargs):
        super(NeededServiceSerializer, self).__init__(**kwargs)
        self._specialized = True

    def __str__(self):
        s = "%s" % (self.service_name)
        if self.link_name:
            s += " (%s)" % (self.link_name)
        if self._specialized:
            s += " -- env: %s" % (self.env)
            s += " -- env_exports: %s" % (self.env_exports)
        return s

    def __repr__(self):
        return "NeededServiceSerializer(service_name=%r, link_name=%r, env=%r, env_exports=%r)" % (self.service_name, self.link_name, self.env, self.env_exports)

    def __eq__(self, other):
        # NeededServiceSerializer objects are equal if equivalent, to deduplicate their instances at runtime
        # objects are not comparable before the call to _validate_(), because fields are not populated yet
        assert self.__has_value__, "NeededServiceSerializer objects are not comparable before validation"
        # easiest implementation for now: handle different link_name as different needed_services; later should try to aggregate various link_names to one instance of NeededServiceSerializer in `service_customization`
        return self.service_name == other.service_name \
            and self.link_name == other.link_name \
            and self.env == other.env

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        # object is not hashable before the call to _validate_(), because fields are not populated yet
        assert self.__has_value__, "NeededServiceSerializer object is not hashable before validation"
        if not hasattr(self, '_env_frozenset'):
            self._env_frozenset = frozenset(self.env.items())
        return hash((self.service_name, self.link_name, self._env_frozenset))

    def _validate_(self, file, needed_migrations, data, field_name):
        # also accept simple variant where data is a string: the service_name
        if common.is_string(data):
            data = {'service_name': data}
        result = super(NeededServiceSerializer, self)._validate_(file, needed_migrations=needed_migrations, data=data, field_name=field_name)
        if self.link_name and \
           not allowed_link_name_pattern.match(self.link_name):
            raise ValidationError("Invalid link name '%s': only '[a-z0-9-]{1,63}' is allowed. " % (self.link_name))
        self._specialized = len(self.env) > 0
        # a unique identifier that is the same for all equivalent NeededServices
        self._id = hash(self)
        common.logger.debug("NeededService _id: %s for %r" % (self._id, self))
        return result

    def get_service_name_unique_suffix(self):
        return "--%s" % (self._id) if self._specialized else ""

class DevConfigSerializer(YAML2PipelineSerializer):
    entrypoint       = FieldSerializer("file", child_path_only = True, executable = True, optional = True, help_text = "Set the entrypoint used with `dmake shell`.")

class ServicesSerializer(YAML2PipelineSerializer):
    service_name    = FieldSerializer("string", default = "", help_text = "The name of the application part.", example = "api", no_slash_no_space = True)
    needed_services = FieldSerializer("array", child = FieldSerializer(NeededServiceSerializer()), default = [], help_text = "List here the sub apps (as defined by service_name) of our application that are needed for this sub app to run.")
    needed_links    = FieldSerializer("array", child = "string", default = [], example = ['mongo'], help_text = "The docker links names to bind to for this test. Must be declared at the root level of some dmake file of the app.")
    sources         = FieldSerializer("array", child = FieldSerializer(["file", "dir"]), optional = True, help_text = "If specified, this service will be considered as updated only when the content of those directories or files have changed.", example = 'path/to/app')
    dev             = DevConfigSerializer(help_text = "Development runtime configuration.")
    config          = DeployConfigSerializer(help_text = "Deployment configuration.")
    tests           = TestSerializer(optional = True, help_text = "Unit tests list.")
    deploy          = DeploySerializer(optional = True, help_text = "Deploy stage")

    def _validate_(self, file, needed_migrations, data, field_name):
        super(ServicesSerializer, self)._validate_(file, needed_migrations=needed_migrations, data=data, field_name=field_name)

        # default internal values
        self.is_variant = False
        self.variant = None
        self.original_service_name = self.service_name

        # populate back-link to this Service
        self.config.docker_image.set_service(self)
        self.deploy.set_service(self)

        return self

    def get_base_image_variant(self):
        return self.config.docker_image.base_image_variant

    def create_variant(self, variant):
        """Create service variant."""
        assert self.get_base_image_variant() is not None, \
            "Create service variants only for services having declared variants"

        service = copy.deepcopy(self)
        service.is_variant = True
        service.variant = variant
        service.__fields__['service_name'].value = "%s:%s" % (service.service_name, variant)
        service.config.docker_image.__fields__['base_image_variant'].value = variant

        return service

    def get_docker_run_gpu_cmd_prefix(self):
        return get_docker_run_gpu_cmd_prefix(self.config.need_gpu, 'service', self.service_name)

    def get_shared_volumes(self):
        return [volume.get_shared_volume() for volume in self.config.volumes if isinstance(volume, SharedVolumeMountSerializer)]

class BuildSerializer(YAML2PipelineSerializer):
    env      = FieldSerializer("dict", child = "string", default = {}, help_text = "List of environment variables used when building applications (excluding base_image).", example = {'BUILD': '${BUILD}'})
    commands = FieldSerializer("array", default = [], child = FieldSerializer(["string", "array"], child = "string", post_validation = lambda x: [x] if common.is_string(x) else x), help_text ="Command list (or list of lists, in which case each list of commands will be executed in paralell) to build.", example = ["cmake .", "make"])

    def _validate_(self, file, needed_migrations, data, field_name):
        super(BuildSerializer, self)._validate_(file, needed_migrations=needed_migrations, data=data, field_name=field_name)
        # populate env
        env = self.__fields__['env'].value
        # variable substitution on env values from dmake process environment
        for key in env:
            env[key] = common.eval_str_in_env(env[key])
        return self


class DMakeFileSerializer(YAML2PipelineSerializer):
    dmake_version      = FieldSerializer("string", help_text = "The dmake version.", example = "0.1")
    app_name           = FieldSerializer("string", help_text = "The application name.", example = "my_app", no_slash_no_space = True)
    blacklist          = FieldSerializer("array", child = "file", default = [], help_text = "List of dmake files to blacklist.", child_path_only = True, example = ['some/sub/dmake.yml'])
    env                = FieldSerializer(["file", EnvSerializer()], optional = True, help_text = "Environment variables to embed in built docker images.")
    volumes            = FieldSerializer("array", child = SharedVolumeSerializer(), default = [], help_text = "List of shared volumes usabled on services and docker_links", example = ['datasets'])
    docker             = FieldSerializer([FieldSerializer("file", help_text = "to another dmake file (which will be added to dependencies) that declares a docker field, in which case it replaces this file's docker field."), DockerSerializer()], help_text = "The environment in which to build and deploy.")
    docker_links       = FieldSerializer("array", child = DockerLinkSerializer(), default = [], help_text = "List of link to create, they are shared across the whole application, so potentially across multiple dmake files.")
    build              = BuildSerializer(help_text = "Commands to run for building the application.")
    pre_test_commands  = FieldSerializer("array", default = [], child = "string", help_text = "Deprecated, not used anymore, will be removed later. Use `tests.commands` instead.")
    post_test_commands = FieldSerializer("array", default = [], child = "string", help_text = "Deprecated, not used anymore, will be removed later. Use `tests.commands` instead.")
    services           = FieldSerializer("array", child = ServicesSerializer(), default = [], help_text = "Service list.")

    def _validate_(self, file, needed_migrations, data, field_name=''):
        super(DMakeFileSerializer, self)._validate_(file, needed_migrations=needed_migrations, data=data, field_name=field_name)
        # fork services with multiple base_image variants, so that each service object has None or one string base_image_variant
        services = []
        for service in self.services:
            variant = service.get_base_image_variant()
            if variant is None or common.is_string(variant):
                services.append(service)
                continue

            # fork service for each base_image variant
            for the_variant in variant:
                service_variant = service.create_variant(the_variant)
                services.append(service_variant)

        self.__fields__['services'].value = services
        return self


class DMakeFile(DMakeFileSerializer):
    def __init__(self, file, data):
        super(DMakeFile, self).__init__()

        self.__path__ = os.path.join(os.path.dirname(file), '')

        try:
            migrated = False

            while True:
                needed_migrations = []
                self._validate_(file, needed_migrations=needed_migrations, data=data)
                if len(needed_migrations) == 0:
                    break
                migrated = True
                needed_migrations.sort()
                for m in needed_migrations:
                    common.logger.info("Applying migration '{}' to '{}'".format(m, file))
                    m = importlib.import_module('migrations.{}'.format(m))
                    data = m.patch(data)
            if migrated:
                with open(file, 'w') as f:
                    common.yaml_ordered_dump(data, f, normalize_indent=True)
                    common.logger.info("Migrations applied, please verify changes in '{}' and commit them.".format(file))

        except ValidationError as e:
            raise DMakeException(("Error in %s:\n" % file) + str(e))

        if self.env is None:
            fake_needed_migrations = []
            env = EnvBranchSerializer()
            env._validate_(file, needed_migrations=fake_needed_migrations, data={'variables': {}})
            self.__fields__['env'] = env
        else:
            if isinstance(self.env, EnvSerializer):
                env = copy.deepcopy(self.env.default)
                if common.branch in self.env.branches:
                    env_branch = self.env.branches[common.branch]
                    for var, value in env_branch.variables.items():
                        env.variables[var] = value
                    env.__fields__['source'].value = env_branch.source
                if env.source is not None:
                    env.__fields__['source'].value = common.eval_str_in_env(env.source)
                else:
                    env.__fields__['source'].value = None
                self.__fields__['env'] = env

        self.docker_services_image = None

        # set common.is_release_branch: does the current branch have a deployment in any dmake.yml file?
        if common.is_release_branch is None:
            common.is_release_branch = False
        if not common.is_release_branch:
            class Found(Exception):
                pass
            try:
                for service in self.services:
                    if not service.deploy.has_value():
                        continue
                    for stage in service.deploy.stages:
                        branches = stage.branches
                        if common.branch in branches or '*' in branches:
                            raise Found
            except Found:
                common.is_release_branch = True
                common.logger.info("Release branch: %s" % common.is_release_branch)

    def get_path(self):
        return self.__path__

    def get_app_name(self):
        return self.app_name

    def get_services(self):
        return self.services

    def get_docker_links(self):
        return self.docker_links

    def get_docker_link(self, link_service_name, docker_links = None):
        if docker_links is None:
            docker_links = {link.link_name: link for link in self.docker_links}
        service = link_service_name.split('/')
        if len(service) != 3:
            raise Exception("Something went wrong: the service should be of the form 'links/:app_name/:link_name'")
        link_name = service[2]
        if link_name not in docker_links:
            raise Exception("Unexpected link '%s'" % link_name)
        link = docker_links[link_name]
        return link

    def _generate_docker_cmd_(self, docker_base, service, env=None, mount_root_dir=True, force_workdir=True):
        if env is None:
            env = {}
        mount_point = docker_base.mount_point

        docker_cmd = ""
        if mount_root_dir:
            docker_cmd += "-v %s:%s " % (common.join_without_slash(common.root_dir), mount_point)
        if force_workdir:
            # `workdir` is in fact only available for Service v1
            if getattr(service.config.docker_image, 'workdir', None) is not None:
                workdir = common.join_without_slash(mount_point, service.config.docker_image.workdir)
            else:
                workdir = os.path.join(mount_point, self.__path__)
            docker_cmd += "-w %s " % (workdir)

        env_file = generate_env_file(common.tmp_dir, env)
        docker_cmd += '--env-file ' + env_file
        return docker_cmd

    def _get_service_(self, service):
        for t in self.services:
            t_name = "%s/%s" % (self.app_name, t.service_name)
            if t_name == service:
                return t
        raise DMakeException("Could not find service '%s'" % service)

    def _get_link_opts_(self, service):
        if common.options.with_dependencies:
            needed_links = service.needed_links + [ns.link_name for ns in service.needed_services if ns.link_name]
            if len(needed_links) > 0:
                return 'dmake_return_docker_links %s %s' % (self.app_name, ' '.join(needed_links))
        return None

    def _get_check_needed_services_(self, commands, service):
        if common.options.with_dependencies and len(service.needed_services) > 0:
            app_name = self.app_name
            # daemon name: <app_name>/<service_name><optional_unique_suffix>; needed_service.service_name doesn't contain app_name
            needed_services = map(lambda needed_service: "%s/%s%s" % (app_name, needed_service.service_name, needed_service.get_service_name_unique_suffix()), service.needed_services)
            append_command(commands, 'sh', shell = "dmake_check_services %s" % (' '.join(needed_services)))

    def _get_shared_volume_from_service_name_(self, shared_volume_service_name):
        for volume in self.volumes:
            if volume.get_service_name() == shared_volume_service_name:
                return volume
        raise DMakeException("Could not find shared_volume service '%s'" % shared_volume_service_name)

    def generate_shared_volume(self, commands, shared_volume_service_name):
        shared_volume = self._get_shared_volume_from_service_name_(shared_volume_service_name)
        shared_volume._serialize_(commands, self.__path__)

    def generate_base(self, commands, base_image_service_name):
        base_image = self.docker.get_base_image_from_service_name(base_image_service_name)
        base_image._serialize_(commands, self.__path__)

    def _generate_run_docker_opts_(self, commands, service, docker_links, additional_env_variables=None, use_host_ports=None):
        docker_opts, env = self._launch_options_(commands, service, docker_links, additional_env_variables=additional_env_variables, run_base_image=False, mount_root_dir=False, force_workdir=False, use_host_ports=use_host_ports)
        image_name = service.config.docker_image.get_image_name(env=env)

        return docker_opts, image_name, env

    def generate_run(self, commands, service_name, docker_links, service_customization):
        service = self._get_service_(service_name)
        if not service.config.docker_image.is_runnable():
            raise DMakeException("You need to specify a 'config.docker_image.start_script' when running service '%s'." % service_name)

        unique_service_name = service_name
        additional_customization_env_variables = {}
        link_name = None
        if service_customization:
            # customization variables will be evaluated later:
            #   by `env.get_replaced_variables()` in the wrong dmake file runtime `.env`, but sometimes OK thanks to needed_links env_exports
            # TODO fix that: customization env should be evaluated in parent service runtime env.
            additional_customization_env_variables = service_customization.env
            # daemon name: <app_name>/<service_name><optional_unique_suffix>; service_name already contains "<app_name>/"
            unique_service_name += service_customization.get_service_name_unique_suffix()
            link_name = service_customization.link_name

        docker_opts, image_name, env = self._generate_run_docker_opts_(commands, service, docker_links, additional_env_variables = additional_customization_env_variables)
        docker_opts += service.tests.get_mounts_opt(service_name, self.__path__, env)
        docker_cmd = 'dmake_run_docker_daemon "%s" "%s" "%s" "" %s -i %s' % (self.app_name, unique_service_name, link_name or "", docker_opts, image_name)
        docker_cmd = service.get_docker_run_gpu_cmd_prefix() + docker_cmd

        # Run daemon
        append_command(commands, 'read_sh', var = "DAEMON_ID", shell = docker_cmd)

        # Wait for daemon to be ready
        cmd = service.config.readiness_probe.get_cmd()
        if cmd:
            append_command(commands, 'sh', shell = 'dmake_exec_docker ${DAEMON_ID} %s' % cmd)

    def generate_build_docker(self, commands, service_name):
        service = self._get_service_(service_name)
        service.config.docker_image.generate_build_docker(commands, self.__path__, self.docker, self.build)

    def _launch_options_(self, commands, service, docker_links, run_base_image, mount_root_dir, force_workdir, additional_env = None, additional_env_variables = None, use_host_ports = None):
        if additional_env is None:
            additional_env = {}

        entrypoint = None
        if run_base_image:
            if service.dev.entrypoint is not None:
                entrypoint = service.dev.entrypoint
            elif getattr(service.config.docker_image, 'entrypoint', None) is not None:
                entrypoint = service.config.docker_image.entrypoint

        if entrypoint:
            full_path_container = os.path.join(self.docker.mount_point,
                                               self.__path__,
                                               entrypoint)
            entrypoint_opt = ' --entrypoint %s' % full_path_container
        else:
            entrypoint_opt = ''

        env = self.env.get_replaced_variables(additional_variables_layers=[service.config.env_override, additional_env_variables], docker_links=docker_links, needed_links=service.needed_links, needed_services=service.needed_services)
        env.update(additional_env)
        docker_opts = self._generate_docker_cmd_(self.docker, service, env=env, mount_root_dir=mount_root_dir, force_workdir=force_workdir)
        docker_opts += entrypoint_opt

        self._get_check_needed_services_(commands, service)
        docker_opts += " " + service.config.full_docker_opts(env, mount_host_volumes=False, use_host_ports=use_host_ports)
        link_opts_command = self._get_link_opts_(service)
        if link_opts_command is not None:
            docker_opts += " $(%s)" % link_opts_command

        return docker_opts, env

    def generate_shell(self, commands, service_name, docker_links, command=None):
        service = self._get_service_(service_name)

        docker_opts, env = self._launch_options_(commands, service, docker_links, run_base_image=True, mount_root_dir=True, force_workdir=True, additional_env=self.build.env)
        docker_opts += service.tests.get_mounts_opt(service_name, self.__path__, env)

        docker_base_image = self.docker.get_docker_base_image(service.get_base_image_variant())
        docker_opts += """ --security-opt="apparmor=unconfined" --cap-add=SYS_PTRACE"""
        docker_opts += " -i %s" % docker_base_image

        docker_cmd = "dmake_run_docker_command %s " % docker_opts
        docker_cmd = service.get_docker_run_gpu_cmd_prefix() + docker_cmd

        if command is None:
            command = self.docker.command
        append_command(commands, 'sh', shell=docker_cmd + command)

    def generate_test(self, commands, service_name, docker_links):
        service = self._get_service_(service_name)
        if not service.tests.has_value():
            # no test specified, nothing to generate for tests
            return

        docker_opts, image_name, env = self._generate_run_docker_opts_(commands, service, docker_links, use_host_ports=False)
        docker_opts += service.tests.get_mounts_opt(service_name, self.__path__, env)
        docker_cmd = 'dmake_run_docker_test %s "" %s -i %s ' % (service_name, docker_opts, image_name)
        docker_cmd = service.get_docker_run_gpu_cmd_prefix() + docker_cmd

        # Run test commands
        service.tests.generate_test(commands, self.__path__, service_name, docker_cmd, docker_links, self.docker.mount_point)

    def generate_run_link(self, commands, service, docker_links):
        link = self.get_docker_link(service, docker_links)
        context_env = self.env.get_replaced_variables()
        image_name = common.eval_str_in_env(link.image_name, context_env)
        options = link.get_options(self.__path__, context_env)
        env = link.get_env(context_env)
        env_file = generate_env_file(common.tmp_dir, env)
        docker_cmd = 'dmake_run_docker_link "%s" "%s" "%s" "%s" --env-file %s %s' % (self.app_name, image_name, link.link_name, link.probe_ports_list(), env_file, options)
        docker_cmd = link.get_docker_run_gpu_cmd_prefix() + docker_cmd
        append_command(commands, 'sh', shell=docker_cmd)

    def generate_deploy(self, commands, service_name):
        service = self._get_service_(service_name)
        if not service.deploy.has_value():
            # no deploy specified, nothing to generate for deploy
            return
        if not service.config.docker_image.is_runnable():
            raise DMakeException("You need to specify a 'config.docker_image.start_script' when deploying service '%s'." % service_name)
        service.deploy.generate_deploy(commands, self.app_name, self.env, service.config)
