import os
import copy
import json
import random
from deepomatic.dmake.serializer import ValidationError, FieldSerializer, YAML2PipelineSerializer
import deepomatic.dmake.common as common
from deepomatic.dmake.common import DMakeException

###############################################################################

def load_env(env):
    if isinstance(env, dict):
        return env

    parsed_env = {}
    with open(env, 'r') as f:
        for line in f.readlines():
            line = line.strip()
            if len(line) == 0 or line[0] == '#':
                continue
            line = line.split("=")
            if len(line) == 1:
                raise ValidationError("Error when parsing %s: expecting VARIABLE=VALUE format" % env)
            var = line[0]
            value = "=".join(line[1:])
            parsed_env[var] = value
    return parsed_env

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
    elif cmd == "sh":
        check_cmd(args, ['shell'])
    elif cmd == "read_sh":
        check_cmd(args, ['var', 'shell'], optional = ['fail_if_empty'])
        args['id'] = len(commands)
        if 'fail_if_empty' not in args:
            args['fail_if_empty'] = False
    elif cmd == "env":
        check_cmd(args, ['var', 'value'])
    elif cmd == "git_tag":
        check_cmd(args, ['tag'])
    elif cmd == "junit":
        check_cmd(args, ['report'])
    elif cmd == "cobertura":
        check_cmd(args, ['report'])
    elif cmd == "publishHTML":
        check_cmd(args, ['directory', 'index', 'title'])
    elif cmd == "build":
        check_cmd(args, ['job', 'parameters', 'propagate', 'wait'])
    else:
        raise DMakeException("Unknow command %s" %cmd)
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
    append_command(commands, 'sh', shell = 'mkdir -p %s && cp -Lr %s %s' % (sub_dir, src, sub_dir))

###############################################################################

def generate_env_file(tmp_dir, env, docker_cmd = False):
    while True:
        file = os.path.join(tmp_dir, 'env.txt.%d' % random.randint(0, 999999))
        if not os.path.isfile(file):
            break
    with open(file, 'w') as f:
        for key, value in env.items():
            value = common.eval_str_in_env(value)
            if docker_cmd:
                f.write('ENV %s "%s"\n' % (key, value))
            else:
                f.write('%s=%s\n' % (key, value))
    return file

def generate_dockerfile(commands, tmp_dir, env):
    file = generate_env_file(tmp_dir, env, True)
    append_command(commands, 'sh', shell = 'dmake_replace_vars_from_file ENV_VARS %s %s %s' % (
        file,
        os.path.join(tmp_dir, 'Dockerfile_template'),
        os.path.join(tmp_dir, 'Dockerfile')))

# ###############################################################################

class EnvBranchSerializer(YAML2PipelineSerializer):
    source    = FieldSerializer('string', optional = True, help_text = 'Source a bash file which defines the environment variables before evaluating the strings of environment variables passed in the *variables* field.')
    variables = FieldSerializer('dict', child = "string", default = {}, help_text = "Defines environment variables used for the services declared in this file. You might use pre-defined environment variables (or variables sourced from the file defined in the *source* field).", example = {'ENV_TYPE': 'dev'})

class EnvSerializer(YAML2PipelineSerializer):
    default  = EnvBranchSerializer(optional = True, help_text = "List of environment variables that will be set by default.")
    branches = FieldSerializer('dict', child = EnvBranchSerializer(), default = {}, help_text = "If the branch matches one of the following fields, those variables will be defined as well, eventually replacing the default.", example = {'master': {'ENV_TYPE': 'prod'}})

class DockerBaseSerializer(YAML2PipelineSerializer):
    name                 = FieldSerializer("string", help_text = "Base image name. If no docker user is indicated, the image will be kept locally")
    version              = FieldSerializer("string", help_text = "Base image version. The branch name will be prefixed to form the docker image tag.", example = "v2", default = 'latest')
    install_scripts      = FieldSerializer("array", default = [], child = FieldSerializer("path", executable = True, child_path_only = True), example = ["some/relative/script/to/run"])
    python_requirements  = FieldSerializer("path", default = "", child_path_only = True, help_text = "Path to python requirements.txt.", example = "")
    python3_requirements = FieldSerializer("path", default = "", child_path_only = True, help_text = "Path to python requirements.txt.", example = "requirements.txt")
    copy_files           = FieldSerializer("array", child = FieldSerializer("path", child_path_only = True), default = [], help_text = "Files to copy. Will be copied before scripts are ran. Paths need to be sub-paths to the build file to preserve MD5 sum-checking (which is used to decide if we need to re-build docker base image). A file 'foo/bar' will be copied in '/base/user/foo/bar'.", example = ["some/relative/file/to/copy"])

class DockerRootImageSerializer(YAML2PipelineSerializer):
    name = FieldSerializer("string", help_text = "Root image name.", example = "library/ubuntu")
    tag  = FieldSerializer("string", help_text = "Root image tag (you can use environment variables).")

    def full_name(self):
        full = self.name + ":" + self.tag
        return common.eval_str_in_env(full)

class DockerSerializer(YAML2PipelineSerializer):
    root_image   = FieldSerializer([FieldSerializer("path", help_text = "to another dmake file, in which base the root_image will be this file's base_image."), DockerRootImageSerializer()], help_text = "The source image name to build on.", example = "ubuntu:16.04")
    base_image   = DockerBaseSerializer(optional = True, help_text = "Base (intermediate) image to speed-up builds.")
    command      = FieldSerializer("string", default = "bash", help_text = "Only used when running 'dmake shell': set the command of the container")

    def _serialize_(self, commands, path_dir):
        if self.base_image.has_value():
            # Make the temporary directory
            tmp_dir = common.run_shell_command('dmake_make_tmp_dir')

            # Copy file and compute their md5
            files_to_copy = []
            for file in self.base_image.copy_files + self.base_image.install_scripts:
                files_to_copy.append(file)
            if self.base_image.python_requirements:
                files_to_copy.append(self.base_image.python_requirements)
            if self.base_image.python3_requirements:
                files_to_copy.append(self.base_image.python3_requirements)

            # Copy file and keep their md5
            md5s = {}
            for file in files_to_copy:
                md5s[file] = common.run_shell_command('dmake_copy_file %s %s' % (os.path.join(path_dir, file), os.path.join(tmp_dir, 'user', file)))

            # Set RUN command
            run_cmd = "cd user"
            for file in self.base_image.install_scripts:
                run_cmd += " && ./%s" % file

            # Install pip if needed
            if self.base_image.python_requirements:
                run_cmd += " && bash ../install_pip.sh && pip install --process-dependency-links -r " + self.base_image.python_requirements
            if self.base_image.python3_requirements:
                run_cmd += " && bash ../install_pip3.sh && pip3 install --process-dependency-links -r " + self.base_image.python3_requirements

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
            local_env.append("export ROOT_IMAGE=%s" % self.root_image)
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
            append_command(commands, 'sh', shell = 'dmake_build_base_docker "%s" "%s" "%s" "%s" "%s"' %
                            (tmp_dir,
                             self.root_image,
                             self.base_image.name,
                             self._get_tag_(),
                             self.base_image.version))

    def _get_tag_(self):
        if common.is_pr:
            prefix = 'pr-%s' % common.pr_id
        else:
            prefix = common.branch
        return 'base-' + prefix + '-' + self.base_image.version

    def get_docker_base_image_name_tag(self):
        if self.base_image.has_value():
            image = self.base_image.name + ":" + self._get_tag_()
            return image
        return self.root_image

class HTMLReportSerializer(YAML2PipelineSerializer):
    directory  = FieldSerializer("string", example = "reports", help_text = "Directory of the html pages.")
    index      = FieldSerializer("string", default = "index.html", help_text = "Main page.")
    title      = FieldSerializer("string", default = "HTML Report", help_text = "Main page title.")

class DockerLinkSerializer(YAML2PipelineSerializer):
    image_name       = FieldSerializer("string", example = "mongo:3.2", help_text = "Name and tag of the image to launch.")
    link_name        = FieldSerializer("string", example = "mongo", help_text = "Link name.")
    deployed_options = FieldSerializer("string", default = "", example = "-v /mnt:/data", help_text = "Additional Docker options when deployed.")
    testing_options  = FieldSerializer("string", default = "", example = "-v /mnt:/data", help_text = "Additional Docker options when testing on Jenkins.")

class AWSBeanStalkDeploySerializer(YAML2PipelineSerializer):
    region      = FieldSerializer("string", default = "eu-west-1", help_text = "The AWS region where to deploy.")
    stack       = FieldSerializer("string", default = "64bit Amazon Linux 2016.03 v2.1.6 running Docker 1.11.2")
    options     = FieldSerializer("path", example = "path/to/options.txt", help_text = "AWS Option file as described here: http://docs.aws.amazon.com/elasticbeanstalk/latest/dg/command-options-general.html")
    credentials = FieldSerializer("string", default = "S3 path to the credential file to aurthenticate a private docker repository.")

    def _serialize_(self, commands, app_name, docker_links, config, image_name, env):
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

        if config.pre_deploy_script  != "" or \
           config.mid_deploy_script  != "" or \
           config.post_deploy_script != "":
            raise DMakeException("Pre/Mid/Post-Deploy scripts for AWS is not supported yet.")
        if len(config.docker_opts) > 0:
            raise DMakeException("Docker options for AWS is not supported yet.")

        # Generate Dockerrun.aws.json
        credentials = self.credentials
        if credentials is not None:
            if credentials.startswith('s3://'):
                credentials = credentials[len('s3://'):]
            elif credentials.find('//') >= 0:
                credentials = None

        credentials = credentials.split('/')
        key = '/'.join(credentials[1:])
        bucket = credentials[0]
        data = {
            "AWSEBDockerrunVersion": "1",
            "Authentication": {
                "Bucket": bucket,
                "Key": key
            },
            "Image": {
                "Name": image_name,
                "Update": "true"
            },
            "Ports": ports,
            "Volumes": volumes,
            "Logging": "/var/log/deepomatic"
        }
        with open(os.path.join(tmp_dir, "Dockerrun.aws.json"), 'w') as dockerrun:
            json.dump(data, dockerrun)

        for var, value in env.items():
            os.environ[var] = common.eval_str_in_env(value)
        option_file = os.path.join(tmp_dir, 'options.txt')
        common.run_shell_command('dmake_replace_vars %s %s' % (self.options, option_file))
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

        append_command(commands, 'sh', shell = 'dmake_deploy_aws_eb "%s" "%s" "%s" "%s"' % (
            tmp_dir,
            app_name,
            self.region,
            self.stack))

class SSHDeploySerializer(YAML2PipelineSerializer):
    user = FieldSerializer("string", example = "ubuntu", help_text = "User name")
    host = FieldSerializer("string", example = "192.168.0.1", help_text = "Host address")
    port = FieldSerializer("int", default = "22", help_text = "SSH port")

    def _serialize_(self, commands, app_name, docker_links, config, image_name, env):
        if not self.has_value():
            return

        tmp_dir = common.run_shell_command('dmake_make_tmp_dir')
        app_name = app_name + "-%s" % common.branch.lower()
        env_file = generate_env_file(tmp_dir, env)

        opts = config.full_docker_opts(False) + " --env-file " + os.path.basename(env_file)

        launch_links = ""
        for link in docker_links:
            launch_links += 'if [ \\`docker ps -f name=%s | wc -l\\` = "1" ]; then set +e; docker rm -f %s 2> /dev/null ; set -e; docker run -d --name %s %s -i %s; fi\n' % (link.link_name, link.link_name, link.link_name, link.deployed_options, link.image_name)
            opts += " --link %s" % link.link_name

        common.run_shell_command('cp -r ${HOME}/.docker* %s/ || :' % tmp_dir)

        start_file = os.path.join(tmp_dir, "start_app.sh")
        common.run_shell_command(
            ('export IMAGE_NAME="%s" && ' % image_name) +
            ('export APP_NAME="%s" && ' % app_name) +
            ('export DOCKER_OPTS="%s" && ' % opts) +
            ('export LAUNCH_LINK="%s" && ' % launch_links) +
            ('export PRE_DEPLOY_HOOKS="%s" && ' % config.pre_deploy_script) +
            ('export MID_DEPLOY_HOOKS="%s" && ' % config.mid_deploy_script) +
            ('export POST_DEPLOY_HOOKS="%s" && ' % config.post_deploy_script) +
             'dmake_copy_template deploy/deploy_ssh/start_app.sh %s' % start_file)

        cmd = 'dmake_deploy_ssh "%s" "%s" "%s" "%s" "%s"' % (tmp_dir, app_name, self.user, self.host, self.port)
        append_command(commands, 'sh', shell = cmd)

class DeployConfigPortsSerializer(YAML2PipelineSerializer):
    container_port    = FieldSerializer("int", example = 8000, help_text = "Port on the container")
    host_port         = FieldSerializer("int", example = 80, help_text = "Port on the host")

class DeployConfigVolumesSerializer(YAML2PipelineSerializer):
    container_volume  = FieldSerializer("string", example = "/mnt", help_text = "Volume on the container")
    host_volume       = FieldSerializer("string", example = "/mnt", help_text = "Volume on the host")

class DeployStageSerializer(YAML2PipelineSerializer):
    description   = FieldSerializer("string", example = "Deployment on AWS and via SSH", help_text = "Deploy stage description.")
    branches      = FieldSerializer(["string", "array"], child = "string", default = ['stag'], post_validation = lambda x: [x] if common.is_string(x) else x, help_text = "Branch list for which this stag is active, '*' can be used to match any branch. Can also be a simple string.")
    env           = FieldSerializer("dict", child = "string", default = {}, example = {'AWS_ACCESS_KEY_ID': '1234', 'AWS_SECRET_ACCESS_KEY': 'abcd'}, help_text = "Additionnal environment variables for deployment.")
    aws_beanstalk = AWSBeanStalkDeploySerializer(optional = True, help_text = "Deploy via Elastic Beanstalk")
    ssh           = SSHDeploySerializer(optional = True, help_text = "Deploy via SSH")

# class InstallExeSerializer(YAML2PipelineSerializer):
#     exe = FieldSerializer("path", child_path_only = True, check_path = False, example = "some/relative/binary", help_text = "Path to the executable to copy (will be copied in /usr/bin).")

#     def docker_cmd(self, commands, path_dir, tmp_dir):
#         generate_copy_command(commands, path_dir, tmp_dir, self.exe)
#         return "COPY %s /usr/bin/" % os.path.basename(self.exe)

#     def docker_opt(self, path_dir):
#         return "-v %s:/usr/bin/%s" % (os.path.join(path_dir, self.exe), os.path.basename(self.exe))

# class InstallLibSerializer(YAML2PipelineSerializer):
#     lib = FieldSerializer("path", child_path_only = True, check_path = False, example = "some/relative/libexample.so", help_text = "Path to the executable to copy (will be copied in /usr/lib).")

#     def docker_cmd(self, commands, path_dir, tmp_dir):
#         generate_copy_command(commands, path_dir, tmp_dir, self.lib)
#         return "COPY %s /usr/lib/" % os.path.basename(self.lib)

#     def docker_opt(self, path_dir):
#         return "-v %s:/usr/lib/%s" % (os.path.join(path_dir, self.lib), os.path.basename(self.lib))

# class InstallDirSerializer(YAML2PipelineSerializer):
#     dir_src = FieldSerializer("dir", child_path_only = True, check_path = False, example = "some/relative/directory/", help_text = "Path to the source directory (relative to this dmake file) to copy.")
#     dir_dst = FieldSerializer("string", check_path = False, help_text = "Path to the install directory (in the docker).")

#     def docker_cmd(self, commands, path_dir, tmp_dir):
#         generate_copy_command(commands, path_dir, tmp_dir, self.dir_src, recursive = True)
#         return "ADD %s %s" % (self.dir_src, self.dir_dst)

#     def docker_opt(self, path_dir):
#         #self.dir_dst start with / and os.path.join would ignore /dmake/volumes if not putting the '+'
#         return '-v %s:%s' % (common.join_without_slash(path_dir, self.dir_src),
#                              common.join_without_slash('/dmake', 'volumes' + self.dir_dst))

class ServiceDockerSerializer(YAML2PipelineSerializer):
    name             = FieldSerializer("string", optional = True, help_text = "Name of the docker image to build. By default it will be {:app_name}-{:service_name}. If there is no docker user, it won be pushed to the registry.")
    check_private    = FieldSerializer("bool", default = True, help_text = "Check that the docker repository is private before pushing the image.")
    tag              = FieldSerializer("string", optional = True, help_text = "Tag of the docker image to build. By default it will be {:branch_name}-{:build_id}")
    workdir          = FieldSerializer("dir", optional = True, help_text = "Working directory of the produced docker file, must be an existing directory. By default it will be directory of the dmake file.")
    #install_targets = FieldSerializer("array", child = FieldSerializer([InstallExeSerializer(), InstallLibSerializer(), InstallDirSerializer()]), default = [], help_text = "Target files or directories to install.")
    copy_directories = FieldSerializer("array", child = "dir", default = [], help_text = "Directories to copy in the docker image.")
    install_script   = FieldSerializer("path", child_path_only = True, executable = True, optional = True, example = "install.sh", help_text = "The install script (will be run in the docker). It has to be executable.")
    entrypoint       = FieldSerializer("path", child_path_only = True, executable = True, optional = True, help_text = "Set the entrypoint of the docker image generated to run the app.")
    start_script     = FieldSerializer("path", child_path_only = True, executable = True, optional = True, example = "start.sh", help_text = "The start script (will be run in the docker). It has to be executable.")

    def get_image_name(self, service_name):
        if self.name is None:
            name = service_name.replace('/', '-')
        else:
            name = self.name
        if self.tag is None:
            tag = common.branch.lower()
            if common.build_id is not None:
                tag += "-%s" % common.build_id
        image_name = name + ":" + tag
        return image_name

    def generate_build_docker(self, commands, path_dir, service_name, docker_base, env, build, config):
        if common.command == "deploy" and self.name is None:
            raise DMakeException('You need to specify an image name for %s in order to deploy the service.' % service_name)

        tmp_dir = common.run_shell_command('dmake_make_tmp_dir')
        common.run_shell_command('mkdir %s' % os.path.join(tmp_dir, 'app'))

        generate_copy_command(commands, tmp_dir, path_dir)
        for d in self.copy_directories:
            if d == path_dir:
                continue
            generate_copy_command(commands, tmp_dir, d)

        dockerfile_template = os.path.join(tmp_dir, 'Dockerfile_template')
        with open(dockerfile_template, 'w') as f:
            f.write('FROM %s\n' % docker_base)
            f.write('${ENV_VARS}\n')
            f.write("ADD app /app\n")

            if self.workdir is not None:
                workdir = self.workdir
            else:
                workdir = path_dir
            workdir = '/app/' + workdir
            f.write('WORKDIR %s\n' % workdir)

            for port in config.ports:
                f.write('EXPOSE %s\n' % port.container_port)

            if build.has_value():
                cmds = []
                for cmd in build.commands:
                    cmds += cmd
                if len(cmds) > 0:
                    cmd = ' && '.join(cmds)
                    f.write('RUN cd %s && %s\n' % (workdir, cmd))

            if self.install_script is not None:
                f.write('RUN cd %s && /app/%s\n' % (workdir, os.path.join(path_dir, self.install_script)))

            if self.start_script is not None:
                f.write('CMD ["/app/%s"]\n' % os.path.join(path_dir, self.start_script))

            if self.entrypoint is not None:
                f.write('ENTRYPOINT ["/app/%s"]\n' % os.path.join(path_dir, self.entrypoint))

        env = copy.deepcopy(env)
        if build.has_value() and build.env.has_value():
            for var, value in build.env.production:
                env[var] = value
        generate_dockerfile(commands, tmp_dir, env)

        image_name = self.get_image_name(service_name)
        append_command(commands, 'sh', shell = 'dmake_build_docker "%s" "%s"' % (tmp_dir, image_name))

        return tmp_dir

class DeployConfigSerializer(YAML2PipelineSerializer):
    docker_image       = ServiceDockerSerializer(optional = True, help_text = "Docker to build for running and deploying")
    docker_links_names = FieldSerializer("array", child = "string", default = [], example = ['mongo'], help_text = "The docker links names to bind to for this test. Must be declared at the root level of some dmake file of the app.")
    docker_opts        = FieldSerializer("string", default = "", example = "--privileged", help_text = "Docker options to add.")
    ports              = FieldSerializer("array", child = DeployConfigPortsSerializer(), default = [], help_text = "Ports to open.")
    volumes            = FieldSerializer("array", child = DeployConfigVolumesSerializer(), default = [], help_text = "Volumes to open.")
    pre_deploy_script  = FieldSerializer("string", default = "", child_path_only = True, example = "my/pre_deploy/script", help_text = "Scripts to run before launching new version.")
    mid_deploy_script  = FieldSerializer("string", default = "", child_path_only = True, example = "my/mid_deploy/script", help_text = "Scripts to run after launching new version and before stopping the old one.")
    post_deploy_script = FieldSerializer("string", default = "", child_path_only = True, example = "my/post_deploy/script", help_text = "Scripts to run after stopping old version.")

    def full_docker_opts(self, testing_mode):
        if not self.has_value():
            return ""

        opts = []
        for ports in self.ports:
            if testing_mode:
                opts.append("-p %s" % ports.container_port)
            else:
                opts.append("-p 0.0.0.0:%s:%s" % (ports.host_port, ports.container_port))

        for volumes in self.volumes:
            if testing_mode:
                host_volume = os.path.join(common.cache_dir, 'volumes', volumes.host_volume)
                try:
                    os.mkdir(host_volume)
                except OSError:
                    pass
            else:
                host_volume = volumes.host_volume

            # On MacOs, the /var directory is actually in /private
            # So you have to activate /private/var in the shard directories
            if common.uname == "Darwin" and host_volume.startswith('/var/'):
                host_volume = '/private/' + host_volume

            opts.append("-v %s:%s" % (common.join_without_slash(host_volume), common.join_without_slash(volumes.container_volume)))

        docker_opts = self.docker_opts
        if testing_mode:
            docker_opts = docker_opts.replace('--privileged', '')
        opts = docker_opts + " " + (" ".join(opts))
        return opts

class DeploySerializer(YAML2PipelineSerializer):
    deploy_name  = FieldSerializer("string", optional = True, example = "", help_text = "The name used for deployment. Will default to \"${DMAKE_DEPLOY_PREFIX}-app_name-service_name\" if not specified")
    stages       = FieldSerializer("array", child = DeployStageSerializer(), help_text = "Deployment possibilities")

    def generate_build_docker(self, commands, path_dir, service_name, docker_base, env, build, config):
        if config.docker_image.has_value():
            config.docker_image.generate_build_docker(commands, path_dir, service_name, docker_base, env, build, config)

    def generate_deploy(self, commands, app_name, service_name, package_dir, docker_links, env, config):
        if self.deploy_name is not None:
            app_name = self.deploy_name
        else:
            app_name = "${DMAKE_DEPLOY_PREFIX}%s-%s" % (app_name, service_name)
        app_name = common.eval_str_in_env(app_name)

        links = []
        for link_name in config.docker_links_names:
            if link_name not in docker_links:
                raise DMakeException("Unknown link name: '%s'" % link_name)
            links.append(docker_links[link_name])

        image_name = config.docker_image.get_image_name(service_name)
        append_command(commands, 'sh', shell = 'dmake_push_docker_image "%s" "%s"' % (image_name, "1" if config.docker_image.check_private else "0"))

        for stage in self.stages:
            branches = stage.branches
            if common.branch not in branches and '*' not in branches:
                continue

            branch_env = copy.deepcopy(env)
            for var, value in stage.env.items():
                branch_env[var] = value

            stage.aws_beanstalk._serialize_(commands, app_name, links, config, image_name, branch_env)
            stage.ssh._serialize_(commands, app_name, links, config, image_name, branch_env)

class TestSerializer(YAML2PipelineSerializer):
    docker_links_names = FieldSerializer("array", child = "string", default = [], example = ['mongo'], help_text = "The docker links names to bind to for this test. Must be declared at the root level of some dmake file of the app.")
    commands           = FieldSerializer("array", child = "string", example = ["python manage.py test"], help_text = "The commands to run for integration tests.")
    junit_report       = FieldSerializer("string", optional = True, example = "test-reports/*.xml", help_text = "Uses JUnit plugin to generate unit test report.")
    cobertura_report   = FieldSerializer("string", optional = True, example = "", help_text = "Publish a Cobertura report (not working for now).")
    html_report        = HTMLReportSerializer(optional = True, help_text = "Publish an HTML report.")

    def generate_test(self, commands, app_name, docker_cmd, docker_links):
        if not self.has_value():
            return

        if common.build_id is None:
            build_id = 0
        else:
            build_id = common.build_id
        for cmd in self.commands:
            d_cmd = "${DOCKER_LINK_OPTS} -e BUILD=%s " % build_id + docker_cmd
            append_command(commands, 'sh', shell = "dmake_run_docker_command " + d_cmd + cmd)

        if self.junit_report is not None:
            append_command(commands, 'junit', report = self.junit_report)

        if self.cobertura_report is not None:
            append_command(commands, 'cobertura', report = self.cobertura_report)

        html = self.html_report._value_()
        if html is not None:
            append_command(commands, 'publishHTML',
                directory = html['directory'],
                index     = html['index'],
                title     = html['title'])

class ServicesSerializer(YAML2PipelineSerializer):
    service_name    = FieldSerializer("string", default = "", help_text = "The name of the application part.", example = "api", no_slash_no_space = True)
    needed_services = FieldSerializer("array", child = FieldSerializer("string", blank = False), default = [], help_text = "List here the sub apps (as defined by service_name) of our application that are needed for this sub app to run.", example = ["worker"])
    sources         = FieldSerializer("array", child = FieldSerializer(["path", "dir"]), optional = True, help_text = "If specified, this service will be considered as updated only when the content of those directories or files have changed.", example = 'path/to/app')
    config          = DeployConfigSerializer(optional = True, help_text = "Deployment configuration.")
    tests           = TestSerializer(optional = True, help_text = "Unit tests list.")
    deploy          = DeploySerializer(optional = True, help_text = "Deploy stage")

class BuildEnvSerializer(YAML2PipelineSerializer):
    testing    = FieldSerializer("dict", child = "string", default = {}, post_validation = load_env, help_text = "List of environment variables that will be set when building for testing.", example = {'MY_ENV_VARIABLE': '1', 'ENV_TYPE': 'dev'})
    production = FieldSerializer("dict", child = "string", default = {}, post_validation = load_env, help_text = "List of environment variables that will be set when building for production.", example = {'MY_ENV_VARIABLE': '1', 'ENV_TYPE': 'dev'})

class BuildSerializer(YAML2PipelineSerializer):
    env      = BuildEnvSerializer(optional = True, help_text = "Environment variable to define when building.")
    commands = FieldSerializer("array", default = [], child = FieldSerializer(["string", "array"], child = "string", post_validation = lambda x: [x] if common.is_string(x) else x), help_text ="Command list (or list of lists, in which case each list of commands will be executed in paralell) to build.", example = ["cmake .", "make"])

class DMakeFileSerializer(YAML2PipelineSerializer):
    dmake_version      = FieldSerializer("string", help_text = "The dmake version.", example = "0.1")
    app_name           = FieldSerializer("string", help_text = "The application name.", example = "my_app", no_slash_no_space = True)
    blacklist          = FieldSerializer("array", child = "path", default = [], help_text = "List of dmake files to blacklist.", child_path_only = True, example = ['some/sub/dmake.yml'])
    env                = FieldSerializer(["path", EnvSerializer()], optional = True, help_text = "Environment variables to embed in built docker images.")
    docker             = FieldSerializer([FieldSerializer("path", help_text = "to another dmake file (which will be added to dependencies) that declares a docker field, in which case it replaces this file's docker field."), DockerSerializer()], help_text = "The environment in which to build and deploy.")
    docker_links       = FieldSerializer("array", child = DockerLinkSerializer(), default = [], help_text = "List of link to create, they are shared across the whole application, so potentially across multiple dmake files.")
    build              = BuildSerializer(optional = True, help_text = "Commands to run for building the application.")
    pre_test_commands  = FieldSerializer("array", default = [], child = "string", help_text = "Command list to run before running tests.")
    post_test_commands = FieldSerializer("array", default = [], child = "string", help_text = "Command list to run after running tests.")
    services           = FieldSerializer("array", child = ServicesSerializer(), default = [], help_text = "Service list.")

class DMakeFile(DMakeFileSerializer):
    def __init__(self, file, data):
        super(DMakeFile, self).__init__()

        self.__path__ = os.path.join(os.path.dirname(file), '')

        try:
            path = os.path.join(os.path.dirname(file), '')
            self._validate_(path, data)
        except ValidationError as e:
            raise DMakeException(("Error in %s:\n" % file) + str(e))

        if self.env is not None and not common.is_string(self.env):
            env = self.env.default
            if common.branch in self.env.branches:
                env_branch = self.env.branches[common.branch]
                variables = copy.deepcopy(env.variables)
                for var, value in env_branch.variables.items():
                    variables[var] = value
                env.__fields__['source'].value = env_branch.source
                env.__fields__['variables'].value = variables
            self.__fields__['env'] = env

        self.env_file = None
        self.docker_services_image = None
        self.app_package_dirs = {}

    def get_app_name(self):
        return self.app_name

    def get_services(self):
        return self.services

    def get_docker_links(self):
        return self.docker_links

    def _generate_env_file_(self):
        if self.env_file is None:
            tmp_dir = common.run_shell_command('dmake_make_tmp_dir')
            env_file = os.path.join(tmp_dir, 'env.txt')

            with open(env_file, 'w') as f:
                for key, value in self.env.items():
                    f.write('%s=%s\n' % (key, value))
            self.env_file = env_file
        return self.env_file

    def _generate_docker_cmd_(self, commands, app_name, env = {}):
        # Set environment variables
        env_file = self._generate_env_file_()

        env_str = []
        for var_value in env.items():
            env_str.append('-e %s=%s' % var_value)
        env_str = " ".join(env_str)

        # Docker command line to run
        docker_cmd = "-v %s:/app -w /app/%s --env-file %s %s -i %s " % (common.join_without_slash(common.root_dir), self.__path__, env_file, env_str, self.docker.get_docker_base_image_name_tag())

        return docker_cmd

    def _get_service_(self, service):
        for t in self.services:
            t_name = "%s/%s" % (self.app_name, t.service_name)
            if t_name == service:
                return t
        raise DMakeException("Could not find service '%s'" % service)

    def _get_link_opts_(self, commands, service):
        docker_links_names = []
        if common.options.dependencies:
            if service.tests.has_value():
                docker_links_names = service.tests.docker_links_names
        else:
            if service.config.has_value():
                docker_links_names = service.config.docker_links_names

        if len(docker_links_names) > 0:
            append_command(commands, 'read_sh', var = 'DOCKER_LINK_OPTS', shell = 'dmake_return_docker_links %s %s' % (self.app_name, ' '.join(docker_links_names)), fail_if_empty = True)

    def _get_check_needed_services_(self, commands, service):
        if common.options.dependencies and len(service.needed_services) > 0:
            app_name = self.app_name
            needed_services = map(lambda service_name: "%s/%s" % (app_name, service_name), service.needed_services)
            append_command(commands, 'sh', shell = "dmake_check_services %s" % (' '.join(needed_services)))

    def generate_base(self, commands):
        self.docker._serialize_(commands, self.__path__)

    def launch_options(self, commands, service, docker_links):
        service = self._get_service_(service)
        workdir = common.join_without_slash('/app', self.__path__)
        if service.config is None:
            entrypoint = None
        else:
            if service.config.docker_image.workdir is not None:
                workdir = common.join_without_slash('/app', service.config.docker_image.workdir)
            entrypoint = service.config.docker_image.entrypoint

        docker_opts = ' -v %s:/app -w %s' % (common.join_without_slash(common.root_dir), workdir)
        if entrypoint is not None:
            full_path_container = os.path.join('/app', self.__path__, entrypoint)
            docker_opts += ' --entrypoint %s' % full_path_container

        self._get_check_needed_services_(commands, service)

        env_file = self._generate_env_file_()

        env_str = []
        if self.build.has_value() and self.build.env.has_value():
            for var, value in self.build.env.testing.items():
                env_str.append('-e %s=%s' % (var, common.eval_str_in_env(value)))
        env_str = " ".join(env_str)

        if common.build_id is None:
            build_id = 0
        else:
            build_id = common.build_id

        self._get_link_opts_(commands, service)
        image_name = self.docker.get_docker_base_image_name_tag()
        opts = docker_opts + " " + service.config.full_docker_opts(True)
        opts = " ${DOCKER_LINK_OPTS} %s --env-file %s -e BUILD=%s %s" % (opts, env_file, build_id, env_str)
        return opts, " -i %s" % image_name

    def generate_shell(self, commands, service, docker_links):
        opts, image_opts = self.launch_options(commands, service, docker_links)
        append_command(commands, 'sh', shell = "dmake_run_docker_command %s %s" % (opts + image_opts, self.docker.command))

    def generate_run(self, commands, service_name, docker_links):
        service = self._get_service_(service_name)
        if service.config is None or service.config.docker_image.start_script is None:
            return

        opts, _ = self.launch_options(commands, service_name, docker_links)
        image_name = service.config.docker_image.get_image_name(service_name)

        if service.config.pre_deploy_script:
            cmd = service.config.pre_deploy_script
            append_command(commands, 'sh', shell = "dmake_run_docker_command %s -i %s %s" % (opts, image_name, cmd))

        daemon_opts = "${DOCKER_LINK_OPTS} %s" % service.config.full_docker_opts(True)
        append_command(commands, 'sh', shell = "dmake_run_docker_daemon \"%s\" \"\" %s -i %s" % (service_name, daemon_opts, image_name))

        cmd = []
        if service.config.mid_deploy_script:
            cmd.append(service.config.mid_deploy_script)
        if service.config.post_deploy_script:
            cmd.append(service.config.post_deploy_script)
        cmd = " && ".join(cmd)
        if cmd:
            cmd = 'bash -c "%s"' % cmd
            append_command(commands, 'sh', shell = "dmake_run_docker_command %s -i %s %s" % (opts, image_name, cmd))

    def generate_build(self, commands):
        if not self.build.has_value():
            return
        env = {}
        if self.build.env.has_value():
            for var, value in self.build.env.testing.items():
                env[var] = common.eval_str_in_env(value)
        docker_cmd = self._generate_docker_cmd_(commands, self.app_name, env)
        for cmds in self.build.commands:
            append_command(commands, 'sh', shell = ["dmake_run_docker_command " + docker_cmd + '%s' % cmd for cmd in cmds])

    def generate_build_docker(self, commands, service_name):
        service = self._get_service_(service_name)
        docker_base = self.docker.get_docker_base_image_name_tag()
        tmp_dir = service.deploy.generate_build_docker(commands, self.__path__, service_name, docker_base, self.env, self.build, service.config)
        self.app_package_dirs[service.service_name] = tmp_dir

    def generate_test(self, commands, service_name, docker_links):
        service = self._get_service_(service_name)
        docker_cmd = self._generate_docker_cmd_(commands, self.app_name)
        docker_cmd = service.config.full_docker_opts(True) + " " + docker_cmd
        if service.config.has_value() and \
           service.config.docker_image.has_value() and \
           service.config.docker_image.entrypoint:
           docker_cmd = (' --entrypoint %s ' % os.path.join('/app', self.__path__, service.config.docker_image.entrypoint)) + docker_cmd
        docker_cmd = ' -e DMAKE_TESTING=1 ' + docker_cmd

        if common.build_id is None:
            build_id = 0
        else:
            build_id = common.build_id

        self._get_check_needed_services_(commands, service)
        self._get_link_opts_(commands, service)
        d_cmd = "dmake_run_docker_command ${DOCKER_LINK_OPTS} -e BUILD=%s " % build_id + docker_cmd

        # Run pre-test commands
        for cmd in self.pre_test_commands:
            append_command(commands, 'sh', shell = d_cmd + cmd)
        # Run test commands
        service.tests.generate_test(commands, self.app_name, docker_cmd, docker_links)
        # Run post-test commands
        for cmd in self.post_test_commands:
            append_command(commands, 'sh', shell = d_cmd + cmd)

    def generate_run_link(self, commands, service, docker_links):
        service = service.split('/')
        if len(service) != 3:
            raise Exception("Something went wrong: the service should be of the form 'links/:app_name/:link_name'")
        link_name = service[2]
        if link_name not in docker_links:
            raise Exception("Unexpected link '%s'" % link_name)
        link = docker_links[link_name]
        append_command(commands, 'sh', shell = 'dmake_run_docker_link "%s" "%s" "%s" "%s"' % (self.app_name, link.image_name, link.link_name, link.testing_options))
        if common.command in ['test']:
            append_command(commands, 'sh', shell = 'sleep 20')

    def generate_deploy(self, commands, service, docker_links):
        service = self._get_service_(service)
        if not service.deploy.has_value():
            return
        if not service.config.has_value():
            raise DMakeException("You need to specify a 'config' when deploying.")
        assert(service.service_name in self.app_package_dirs)
        service.deploy.generate_deploy(commands, self.app_name, service.service_name, self.app_package_dirs[service.service_name], docker_links, self.env, service.config)
