import os, sys
import copy
import json
import random
import time
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

def generate_copy_command(commands, path_dir, tmp_dir, file_or_dir, recursive = False):
    src = os.path.join(path_dir, file_or_dir)
    dst = os.path.join(tmp_dir, file_or_dir)
    d = os.path.dirname(dst)
    append_command(commands, 'sh', shell = 'mkdir -p %s && cp %s %s %s' % (d, '-r' if recursive else '', src, dst))

###############################################################################

def generate_dockerfile(commands, tmp_dir, env):
    while True:
        file = os.path.join(tmp_dir, 'env.txt.%d' % random.randint(0, 999999))
        if not os.path.isfile(file):
            break
    with open(file, 'w') as f:
        for key, value in env.items():
            value = common.eval_str_in_env(value)
            f.write('ENV %s "%s"\n' % (key, value.replace('"', '\\"')))
    append_command(commands, 'sh', shell = 'dmake_replace_vars_from_file ENV_VARS %s %s %s' % (
        file,
        os.path.join(tmp_dir, 'Dockerfile_template'),
        os.path.join(tmp_dir, 'Dockerfile')))

# ###############################################################################

class EnvSerializer(YAML2PipelineSerializer):
    default  = FieldSerializer([FieldSerializer("path", help_text = "to another dmake file that declares a default environment."), "dict"], child = "string", default = {}, post_validation = load_env, help_text = "List of environment variables that will be set by default.", example = {'MY_ENV_VARIABLE': '1', 'ENV_TYPE': 'dev'})
    branches = FieldSerializer("dict", child = FieldSerializer("dict", child = "string"), default = {}, help_text = "If the branch matches one of the following fields, those variables will be defined as well, eventually replacing the default.", example = {'master': {'ENV_TYPE': 'prod'}})

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

            # HACK: copy key while #493 is not closed: https://github.com/docker/for-mac/issues/483
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
    region   = FieldSerializer("string", default = "eu-west-1", help_text = "The AWS region where to deploy.")
    stack    = FieldSerializer("string", default = "64bit Amazon Linux 2016.03 v2.1.6 running Docker 1.11.2")
    options  = FieldSerializer("path", example = "path/to/options.txt", help_text = "AWS Option file as described here: http://docs.aws.amazon.com/elasticbeanstalk/latest/dg/command-options-general.html")

    def _serialize_(self, commands, tmp_dir, app_name, docker_links, config):
        if not self.has_value():
            return

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
        data = {
            "AWSEBDockerrunVersion": "1",
            # "Authentication": {
            #     "Bucket": "my-bucket",
            #     "Key": "mydockercfg"
            # },
            # "Image": {
            #     "Name": "quay.io/johndoe/private-image",
            #     "Update": "true"
            # },
            "Ports": ports,
            "Volumes": volumes,
            "Logging": "/var/log/deepomatic"
        }
        with open(os.path.join(tmp_dir, "Dockerrun.aws.json"), 'w') as dockerrun:
            json.dump(data, dockerrun)

        common.run_shell_command('dmake_replace_vars %s %s' % (self.options, os.path.join(tmp_dir, 'options.txt')))

        append_command(commands, 'sh', shell = 'dmake_deploy_aws_eb "%s" "%s" "%s" "%s"' % (
            tmp_dir,
            app_name,
            self.region,
            self.stack))

class SSHDeploySerializer(YAML2PipelineSerializer):
    user = FieldSerializer("string", example = "ubuntu", help_text = "User name")
    host = FieldSerializer("string", example = "192.168.0.1", help_text = "Host address")
    port = FieldSerializer("int", default = "22", help_text = "SSH port")

    def _serialize_(self, commands, tmp_dir, app_name, docker_links, config):
        if not self.has_value():
            return

        opts = config.full_docker_opts(False)

        launch_links = ""
        for link in docker_links:
            launch_links += 'if [ \\`docker ps -f name=%s | wc -l\\` = "1" ]; then set +e; docker rm -f %s 2> /dev/null ; set -e; docker run -d --name %s %s -i %s; fi\n' % (link.link_name, link.link_name, link.link_name, link.deployed_options, link.image_name)
            opts += " --link %s" % link.link_name

        common.run_shell_command('export APP_NAME="%s" && export DOCKER_OPTS="%s" && export LAUNCH_LINK="%s" && export PRE_DEPLOY_HOOKS="%s" && export MID_DEPLOY_HOOKS="%s" && export POST_DEPLOY_HOOKS="%s" && dmake_copy_template deploy/deploy_ssh/start_app.sh %s && dmake_copy_template deploy/deploy_ssh/start_cmd.sh %s' % (
            app_name + "-%s" % common.branch.lower(),
            opts,
            launch_links,
            config.pre_deploy_script,
            config.mid_deploy_script,
            config.post_deploy_script,
            os.path.join(tmp_dir, "start_app.sh"),
            os.path.join(tmp_dir, "start_cmd.sh")))

        cmd = 'dmake_deploy_ssh "%s" "%s" "%s" "%s"' % (
                tmp_dir,
                self.user,
                self.host,
                self.port)
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

class InstallExeSerializer(YAML2PipelineSerializer):
    exe = FieldSerializer("path", child_path_only = True, check_path = False, example = "some/relative/binary", help_text = "Path to the executable to copy (will be copied in /usr/local/bin).")
    def docker_cmd(self, commands, path_dir, tmp_dir):
        generate_copy_command(commands, path_dir, tmp_dir, self.exe)
        return "COPY %s /usr/local/bin/" % self.exe

class InstallLibSerializer(YAML2PipelineSerializer):
    lib = FieldSerializer("path", child_path_only = True, check_path = False, example = "some/relative/libexample.so", help_text = "Path to the executable to copy (will be copied in /usr/local/lib).")
    def docker_cmd(self, commands, path_dir, tmp_dir):
        generate_copy_command(commands, path_dir, tmp_dir, self.lib)
        return "COPY %s /usr/local/lib/" % self.lib

class InstallDirSerializer(YAML2PipelineSerializer):
    dir_src = FieldSerializer("dir", child_path_only = True, check_path = False, example = "some/relative/directory/", help_text = "Path to the source directory (relative to this dmake file) to copy.")
    dir_dst = FieldSerializer("string", check_path = False, help_text = "Path to the install directory (in the docker).")
    def docker_cmd(self, commands, path_dir, tmp_dir):
        generate_copy_command(commands, path_dir, tmp_dir, self.dir_src, recursive = True)
        return "ADD %s %s" % (self.dir_src, self.dir_dst)

class ServiceDockerSerializer(YAML2PipelineSerializer):
    workdir         = FieldSerializer("string", default = "/", help_text = "Working directory of the produced docker file.")
    install_targets = FieldSerializer("array", child = FieldSerializer([InstallExeSerializer(), InstallLibSerializer(), InstallDirSerializer()]), default = [], help_text = "Target files or directories to install.")
    install_script  = FieldSerializer("path", child_path_only = True, executable = True, optional = True, example = "install.sh", help_text = "The install script (will be run in the docker). It has to be executable.")
    entrypoint      = FieldSerializer("path", child_path_only = True, executable = True, optional = True, help_text = "Set the entrypoint of the docker image generated to run the app.")
    start_script    = FieldSerializer("path", child_path_only = True, executable = True, optional = True, example = "start.sh", help_text = "The start script (will be run in the docker). It has to be executable.")

    def get_image_name(self, app_name, service_name):
        image_name = "%s-%s:%s" % (app_name, service_name, common.branch.lower())
        if common.build_id is not None:
            image_name += '.' + common.build_id
        return image_name

    def generate_build(self, commands, path_dir, app_name, service_name, docker_base, env, config):
        tmp_dir = common.run_shell_command('dmake_make_tmp_dir')

        dockerfile_template = os.path.join(tmp_dir, 'Dockerfile_template')
        with open(dockerfile_template, 'w') as f:
            f.write('FROM %s\n' % docker_base)
            f.write('\n')
            f.write('${ENV_VARS}\n')
            f.write('\n')
            f.write('WORKDIR %s\n' % self.workdir)
            f.write('\n')
            for port in config.ports:
                f.write('EXPOSE %s\n' % port.container_port)
            f.write('\n')
            for target in self.install_targets:
                f.write(target.docker_cmd(commands, path_dir, tmp_dir) + "\n")
            f.write('\n')

            if self.install_script is not None:
                generate_copy_command(commands, path_dir, tmp_dir, self.install_script)
                f.write('COPY %s %s\n' % (
                    self.install_script,
                    os.path.join(self.workdir, self.install_script)))
                f.write('RUN cd %s && ./%s\n' % (self.workdir, self.install_script))

            if self.start_script is not None:
                generate_copy_command(commands, path_dir, tmp_dir, self.start_script)
                f.write('COPY %s %s\n' % (
                    self.start_script,
                    os.path.join(self.workdir, self.start_script)))
                f.write('CMD ["./%s"]\n' % self.start_script)

            if self.entrypoint is not None:
                f.write('ENTRYPOINT ["./%s"]\n' % self.entrypoint)

        generate_dockerfile(commands, tmp_dir, env)

        image_name = self.get_image_name(app_name, service_name)
        append_command(commands, 'sh', shell = 'dmake_build_docker "%s" "%s"' % (tmp_dir, image_name))
        return tmp_dir

class DeployConfigSerializer(YAML2PipelineSerializer):
    docker_image       = ServiceDockerSerializer(help_text = "Docker to build for running and deploying")
    docker_links_names = FieldSerializer("array", child = "string", default = [], example = ['mongo'], help_text = "The docker links names to bind to for this test. Must be declared at the root level of some dmake file of the app.")
    docker_opts        = FieldSerializer("string", default = "", example = "--privileged", help_text = "Docker options to add.")
    ports              = FieldSerializer("array", child = DeployConfigPortsSerializer(), default = [], help_text = "Ports to open.")
    volumes            = FieldSerializer("array", child = DeployConfigVolumesSerializer(), default = [], help_text = "Volumes to open.")
    pre_deploy_script  = FieldSerializer("string", default = "", child_path_only = True, example = "my/pre_deploy/script", help_text = "Scripts to run before launching new version.")
    mid_deploy_script  = FieldSerializer("string", default = "", child_path_only = True, example = "my/mid_deploy/script", help_text = "Scripts to run after launching new version and before stopping the old one.")
    post_deploy_script = FieldSerializer("string", default = "", child_path_only = True, example = "my/post_deploy/script", help_text = "Scripts to run after stopping old version.")

    def full_docker_opts(self, testing_mode):
        opts = []
        for ports in self.ports:
            opts.append("-p 0.0.0.0:%s:%s" % (ports.host_port, ports.container_port))

        for volumes in self.volumes:
            if testing_mode and not common.is_local:
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

        opts = self.docker_opts + " " + (" ".join(opts))
        return opts

class DeploySerializer(YAML2PipelineSerializer):
    deploy_name  = FieldSerializer("string", optional = True, example = "", help_text = "The name used for deployment. Will default to \"db-app_name-service_name\" if not specified")
    stages       = FieldSerializer("array", child = DeployStageSerializer(), help_text = "Deployment possibilities")

    _tmp_dir_    = None

    def generate_build(self, commands, path_dir, app_name, service_name, docker_base, env, config):
        if self._tmp_dir_ is not None:
            raise DMakeException('Build already generated')

        if config.docker_image.has_value():
            self._tmp_dir_ = config.docker_image.generate_build(commands, path_dir, app_name, service_name, docker_base, env, config)

    def generate_deploy(self, commands, app_name, service_name, docker_links, env, config):
        if self._tmp_dir_ is None:
            raise DMakeException('Sanity check failed: it seems the build step has been skipped: _tmp_dir_ is null.')

        if self.deploy_name is not None:
            app_name = self.deploy_name
        else:
            app_name = "dp-%s-%s" % (app_name, service_name)

        links = []
        for link_name in config.docker_links_names:
            if link_name not in docker_links:
                raise DMakeException("Unknown link name: '%s'" % link_name)
            links.append(docker_links[link_name])

        for stage in self.stages:
            branches = stage.branches
            if common.branch not in branches and '*' not in branches:
                continue

            env = copy.deepcopy(env)
            for var, value in stage.env.items():
                env[var] = value
                os.environ[var] = value

            generate_dockerfile(commands, self._tmp_dir_, env)

            stage.aws_beanstalk._serialize_(commands, self._tmp_dir_, app_name, links, config)
            stage.ssh._serialize_(commands, self._tmp_dir_, app_name, links, config)

class TestsSerializer(YAML2PipelineSerializer):
    docker_links_names = FieldSerializer("array", child = "string", default = [], example = ['mongo'], help_text = "The docker links names to bind to for this test. Must be declared at the root level of some dmake file of the app.")
    docker_opts        = FieldSerializer("string", default = "", example = "--privileged", help_text = "Docker options to add when testing or launching.")
    commands           = FieldSerializer("array", child = "string", example = ["python manage.py test"], help_text = "The commands to run for integration tests.")
    junit_report       = FieldSerializer("string", optional = True, example = "test-reports/*.xml", help_text = "Uses JUnit plugin to generate unit test report.")
    cobertura_report   = FieldSerializer("string", optional = True, example = "", help_text = "Publish a Cobertura report (not working for now).")
    html_report        = HTMLReportSerializer(optional = True, help_text = "Publish an HTML report.")

    def generate_test(self, commands, app_name, docker_cmd, docker_links):
        for cmd in self.commands:
            d_cmd = "${DOCKER_LINK_OPTS} -e BUILD=%s -e DMAKE_TESTING=1 " % (common.build_id) + self.docker_opts + docker_cmd
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
    tests           = TestsSerializer(optional = True, help_text = "Unit tests list.")
    deploy          = DeploySerializer(optional = True, help_text = "Deploy stage")

class DMakeFileSerializer(YAML2PipelineSerializer):
    dmake_version            = FieldSerializer("string", help_text = "The dmake version.", example = "0.1")
    app_name                 = FieldSerializer("string", help_text = "The application name.", example = "my_app", no_slash_no_space = True)
    blacklist                = FieldSerializer("array", child = "path", default = [], help_text = "List of dmake files to blacklist.", child_path_only = True, example = ['some/sub/dmake.yml'])
    env                      = EnvSerializer(help_text = "Environment variables to embed in built docker images.")
    docker                   = FieldSerializer([FieldSerializer("path", help_text = "to another dmake file (which will be added to dependencies) that declares a docker field, in which case it replaces this file's docker field."), DockerSerializer()], help_text = "The environment in which to build and deploy.")
    docker_links             = FieldSerializer("array", child = DockerLinkSerializer(), default = [], help_text = "List of link to create, they are shared across the whole application, so potentially across multiple dmake files.")
    build_tests_commands     = FieldSerializer("array", default = [], child = FieldSerializer(["string", "array"], child = "string", post_validation = lambda x: [x] if common.is_string(x) else x), help_text ="Command list (or list of lists, in which case each list of commands will be executed in paralell) to build.", example = ["cmake .", "make"])
    build_services_commands  = FieldSerializer("array", default = [], child = FieldSerializer(["string", "array"], child = "string", post_validation = lambda x: [x] if common.is_string(x) else x), help_text ="Command list (or list of lists, in which case each list of commands will be executed in paralell) to build.", example = ["cmake .", "make"])
    services                 = FieldSerializer("array", child = ServicesSerializer(), default = [], help_text = "Service list.")

class DMakeFile(DMakeFileSerializer):
    def __init__(self, file, data):
        super(DMakeFile, self).__init__()

        self.__path__ = os.path.join(os.path.dirname(file), '')

        try:
            path = os.path.join(os.path.dirname(file), '')
            self._validate_(path, data)
        except ValidationError as e:
            raise DMakeException(("Error in %s:\n" % file) + str(e))

        if self.env.__has_value__:
            env = copy.deepcopy(self.env.default)
            if common.branch in self.env.branches:
                for var, value in self.env.branches[common.branch].items():
                    env[var] = value

            env_field = FieldSerializer("dict", child = "string")
            env_field._validate_(self.__path__, env)
            self.__fields__['env'] = env_field
        else:
            self.__fields__['env'] = {}

        self.env_file = None
        self.docker_cmd = None
        self.docker_services_image = None

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
                    value = common.eval_str_in_env(value)
                    f.write('%s=%s\n' % (key, value))
            self.env_file = env_file
        return self.env_file

    def _generate_docker_cmd_(self, commands, app_name):
        if self.docker_cmd is None:
            # Set environment variables
            env_file = self._generate_env_file_()

            # Docker command line to run
            self.docker_cmd = "-v %s:/app -w /app/%s --env-file %s -e ENV_TYPE=%s -i %s " % (common.join_without_slash(common.root_dir), self.__path__, env_file, common.env_type, self.docker.get_docker_base_image_name_tag())

        return self.docker_cmd

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

    def generate_shell(self, commands, service, services, docker_links):
        service = self._get_service_(service)
        if service.config is None:
            workdir = '/app'
            entrypoint = None
        else:
            workdir = service.config.docker_image.workdir
            entrypoint = service.config.docker_image.entrypoint

        docker_opts='-v %s:%s -w %s' % (common.join_without_slash(common.root_dir, self.__path__), workdir, workdir)
        if entrypoint is not None:
            full_path_container = os.path.join(workdir, entrypoint)
            docker_opts += ' --entrypoint %s' % full_path_container

        self._get_check_needed_services_(commands, service)

        image_name = self.docker.get_docker_base_image_name_tag()
        env_file = self._generate_env_file_()
        self._get_link_opts_(commands, service)
        opts = docker_opts + " " + service.config.full_docker_opts(True)
        opts = " ${DOCKER_LINK_OPTS} %s --env-file %s -e ENV_TYPE=%s -e BUILD=%s -i %s " % (opts, env_file, common.env_type, common.build_id, image_name)
        append_command(commands, 'sh', shell = "dmake_run_docker \"\" \"\" --rm -t " + opts + " " + self.docker.command)

    def generate_build_tests(self, commands):
        docker_cmd = self._generate_docker_cmd_(commands, self.app_name)
        for cmds in self.build_tests_commands:
            append_command(commands, 'sh', shell = ["dmake_run_docker_command " + docker_cmd + '%s' % cmd for cmd in cmds])

    def generate_build_services(self, commands):
        docker_cmd = self._generate_docker_cmd_(commands, self.app_name)
        for cmds in self.build_services_commands:
            append_command(commands, 'sh', shell = ["dmake_run_docker_command " + docker_cmd + cmd for cmd in cmds])

    def generate_build(self, commands, service):
        service = self._get_service_(service)
        docker_base = self.docker.get_docker_base_image_name_tag()
        service.deploy.generate_build(commands, self.__path__, self.app_name, service.service_name, docker_base, self.env, service.config)

    def generate_test(self, commands, service, services, docker_links):
        service = self._get_service_(service)
        docker_cmd = self._generate_docker_cmd_(commands, self.app_name)
        if service.config.has_value() and service.config.docker_image.entrypoint:
           docker_cmd = (' --entrypoint %s ' % os.path.join('/app', self.__path__, service.config.docker_image.entrypoint)) + docker_cmd

        self._get_check_needed_services_(commands, service)
        self._get_link_opts_(commands, service)
        service.tests.generate_test(commands, self.app_name, docker_cmd, docker_links)

    def generate_run(self, commands, service, docker_links):
        service_name = service
        service = self._get_service_(service)

        self._get_check_needed_services_(commands, service)

        image_name = service.config.docker_image.get_image_name(self.app_name, service.service_name)
        self._get_link_opts_(commands, service)
        opts = service.config.full_docker_opts(True)
        opts = " ${DOCKER_LINK_OPTS} " + opts + " -e BUILD=%s -e DMAKE_TESTING=1 -i %s " % (common.build_id, image_name)
        append_command(commands, 'sh', shell = "ID=$(dmake_run_docker_daemon \"" + service_name + "\" \"\" " + opts + ") && echo \"Launched daemon for %s with ID: ${ID}\"" % image_name)
        append_command(commands, 'sh', shell = "sleep 2") # wait a bit for worker to start, so that potential crash at start-up have time to occur

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

        service.deploy.generate_deploy(commands, self.app_name, service.service_name, docker_links, self.env, service.config)
