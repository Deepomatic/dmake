from deepomatic.dmake.dmake_file import DMakeFileAbstract
from deepomatic.dmake.action import Action
import deepomatic.dmake.common as common

import actions.base as base
import serializers

###############################################################################

class DMakeFile(DMakeFileAbstract):
    def __init__(self, service_managers, file, data):
        self.serializer = serializers.DMakeFileSerializer()
        super(DMakeFile, self).__init__(service_managers, file, data)

        self._register_action_(base.GetBaseMD5)
        self._register_action_(base.BuildBaseDockerFromFile)
        self._register_action_(base.BuildBaseDockerFromService)

    def get_app_name(self):
        return self.serializer.app_name

    def get_black_list(self):
        return self.serializer.blacklist

    def register_services(self):
        for s in self.serializer.services:
            docker_image_name = None
            if s.config.has_value() and \
               s.config.docker_image.has_value() and \
               s.config.docker_image.name:
                docker_image_name = s.config.docker_image.name

            test_dependencies = []
            if s.tests.has_value():
                test_dependencies = s.tests.docker_links_names
            self._register_service_(
                False,
                s.service_name,
                docker_image_name,
                s.needed_services,
                test_dependencies)

        for l in self.serializer.docker_links:
            self._register_service_(True, l.link_name, l.image_name)

    ###########################################################################

    # class BuildApp(Action):
    #     stage = 'build'
    #     args  = ['context']
    #     def _generate_(self, dmake_file, service, context):
    #         self.request('BaseDocker', service)

    # class BuildAppDocker(Action):
    #     stage = 'docker'
    #     args  = ['context']
    #     def _generate_(self, dmake_file, service, context):
    #         pass

    # class Run(Action):
    #     stage = 'run'
    #     args  = ['context', 'env']
    #     def _generate_(self, dmake_file, service, context, env):
    #         pass

    # class Test(Action):
    #     stage = 'test'
    #     def _generate_(self, dmake_file, service):
    #         pass

    # class Deploy(Action):
    #     stage = 'deploy'
    #     def _generate_(self, dmake_file, service):
    #         pass

    ###############################################################################

    class ShellCommand(Action):
        stage = 'command'
        def _generate_(self, dmake_file, service):
            pass

    class DeployCommand(Action):
        stage = 'command'
        def _generate_(self, dmake_file, service):
            self.request('BuildBaseDockerFromService', service.get_name())

    class TestCommand(Action):
        stage = 'command'
        def _generate_(self, dmake_file, service):
            pass

    #------------------------------------------------------------------------------










    # def get_path(self):
    #     return self.__path__

    # def get_services(self):
    #     return self.services

    # def get_docker_links(self):
    #     return self.docker_links

    # def _generate_env_flags_(self, additional_variables = {}):
    #     flags = []
    #     for key, value in self.env.get_replaced_variables(additional_variables).items():
    #         flags.append('-e %s=%s' % (key, common.wrap_cmd(value)))
    #     return " ".join(flags)

    # def _generate_docker_cmd_(self, env = {}, workdir = None):
    #     if workdir is None:
    #         workdir = os.path.join('/app/', self.__path__)
    #     docker_cmd = "-v %s:/app -w %s " % (common.join_without_slash(common.root_dir), workdir)
    #     docker_cmd += self._generate_env_flags_(env)
    #     return docker_cmd

    # def _get_service_(self, service):
    #     for t in self.services:
    #         t_name = "%s/%s" % (self.app_name, t.service_name)
    #         if t_name == service:
    #             return t
    #     raise DMakeException("Could not find service '%s'" % service)

    # def _get_link_opts_(self, commands, service):
    #     docker_links_names = []
    #     if common.options.dependencies:
    #         if service.tests.has_value():
    #             docker_links_names = service.tests.docker_links_names
    #     else:
    #         if service.config.has_value():
    #             docker_links_names = service.config.docker_links_names

    #     if len(docker_links_names) > 0:
    #         append_command(commands, 'read_sh', var = 'DOCKER_LINK_OPTS', shell = 'dmake_return_docker_links %s %s' % (self.app_name, ' '.join(docker_links_names)), fail_if_empty = True)

    # def _get_check_needed_services_(self, commands, service):
    #     if common.options.dependencies and len(service.needed_services) > 0:
    #         app_name = self.app_name
    #         needed_services = map(lambda service_name: "%s/%s" % (app_name, service_name), service.needed_services)
    #         append_command(commands, 'sh', shell = "dmake_check_services %s" % (' '.join(needed_services)))

    # def generate_base(self, commands):
    #     self.docker._serialize_(commands, self.__path__)

    # def generate_run(self, commands, service_name, docker_links):
    #     service = self._get_service_(service_name)
    #     if service.config is None or service.config.docker_image.start_script is None:
    #         return

    #     opts = self._launch_options_(commands, service, docker_links)
    #     image_name = service.config.docker_image.get_image_name(service_name)

    #     # <DEPRECATED>
    #     if service.config.pre_deploy_script:
    #         cmd = service.config.pre_deploy_script
    #         append_command(commands, 'sh', shell = "dmake_run_docker_command %s -i %s %s" % (opts, image_name, cmd))
    #     # </DEPRECATED>

    #     daemon_opts = "${DOCKER_LINK_OPTS} %s" % service.config.full_docker_opts(True)
    #     append_command(commands, 'read_sh', var = "DAEMON_ID", shell = 'dmake_run_docker_daemon "%s" "" %s -i %s' % (service_name, daemon_opts, image_name))

    #     cmd = service.config.readiness_probe.get_cmd()
    #     if cmd:
    #         append_command(commands, 'sh', shell = 'dmake_exec_docker "$DAEMON_ID" %s' % cmd)

    #     # <DEPRECATED>
    #     cmd = []
    #     if service.config.mid_deploy_script:
    #         cmd.append(service.config.mid_deploy_script)
    #     if service.config.post_deploy_script:
    #         cmd.append(service.config.post_deploy_script)
    #     cmd = " && ".join(cmd)
    #     if cmd:
    #         cmd = 'bash -c %s' % common.wrap_cmd(cmd)
    #         append_command(commands, 'sh', shell = "dmake_run_docker_command %s -i %s %s" % (opts, image_name, cmd))
    #     # </DEPRECATED>

    # def generate_build(self, commands):
    #     if not self.build.has_value():
    #         return
    #     env = {}
    #     if self.build.env.has_value():
    #         for var, value in self.build.env.testing.items():
    #             env[var] = common.eval_str_in_env(value)
    #     docker_cmd = self._generate_docker_cmd_(env)
    #     docker_cmd += ' -e DMAKE_TESTING=1 '
    #     docker_cmd += " -i %s " % self.docker.get_docker_base_image_name_tag()

    #     for cmds in self.build.commands:
    #         append_command(commands, 'sh', shell = ["dmake_run_docker_command " + docker_cmd + ' %s' % cmd for cmd in cmds])

    # def generate_build_docker(self, commands, service_name):
    #     service = self._get_service_(service_name)
    #     docker_base = self.docker.get_docker_base_image_name_tag()
    #     tmp_dir = service.deploy.generate_build_docker(commands, self.__path__, service_name, docker_base, self.env, self.build, service.config)
    #     self.app_package_dirs[service.service_name] = tmp_dir

    # def _launch_options_(self, commands, service, docker_links, env = {}):
    #     workdir = common.join_without_slash('/app', self.__path__)
    #     if not service.config.has_value() or not service.config.docker_image.has_value():
    #         entrypoint = None
    #     else:
    #         if service.config.docker_image.workdir is not None:
    #             workdir = common.join_without_slash('/app', service.config.docker_image.workdir)
    #         entrypoint = service.config.docker_image.entrypoint

    #     docker_opts = self._generate_docker_cmd_(env, workdir)
    #     if entrypoint is not None:
    #         full_path_container = os.path.join('/app', self.__path__, entrypoint)
    #         docker_opts += ' --entrypoint %s' % full_path_container

    #     build_id = common.build_id if common.build_id else "0"
    #     self._get_check_needed_services_(commands, service)
    #     self._get_link_opts_(commands, service)
    #     docker_opts += " " + service.config.full_docker_opts(True)
    #     docker_opts += " ${DOCKER_LINK_OPTS} -e BUILD=%s" % build_id

    #     return docker_opts

    # def _generate_test_docker_cmd_(self, commands, service, docker_links):
    #     env = self.build.env.testing if self.build.has_value() and \
    #                                     self.build.env.has_value() else {}
    #     docker_opts  = self._launch_options_(commands, service, docker_links, env)

    #     if service.tests.has_value():
    #         opts=[]
    #         for data_volume in service.tests.data_volumes:
    #             opts.append(data_volume.get_mount_opt())
    #         docker_opts += " " + (" ".join(opts))

    #     docker_opts += " -e DMAKE_TESTING=1 -i %s" % self.docker.get_docker_base_image_name_tag()

    #     return "dmake_run_docker_command %s " % docker_opts

    # def generate_shell(self, commands, service_name, docker_links):
    #     service = self._get_service_(service_name)
    #     docker_cmd = self._generate_test_docker_cmd_(commands, service, docker_links)
    #     append_command(commands, 'sh', shell = docker_cmd + self.docker.command)

    # def generate_test(self, commands, service_name, docker_links):
    #     service = self._get_service_(service_name)
    #     docker_cmd = self._generate_test_docker_cmd_(commands, service, docker_links)

    #     # Run pre-test commands
    #     for cmd in self.pre_test_commands:
    #         append_command(commands, 'sh', shell = docker_cmd + cmd)
    #     # Run test commands
    #     service.tests.generate_test(commands, self.app_name, docker_cmd, docker_links)
    #     # Run post-test commands
    #     for cmd in self.post_test_commands:
    #         append_command(commands, 'sh', shell = docker_cmd + cmd)

    # def generate_run_link(self, commands, service, docker_links):
    #     service = service.split('/')
    #     if len(service) != 3:
    #         raise Exception("Something went wrong: the service should be of the form 'links/:app_name/:link_name'")
    #     link_name = service[2]
    #     if link_name not in docker_links:
    #         raise Exception("Unexpected link '%s'" % link_name)
    #     link = docker_links[link_name]
    #     append_command(commands, 'sh', shell = 'dmake_run_docker_link "%s" "%s" "%s" "%s" "%s"' % (self.app_name, link.image_name, link.link_name, link.testing_options, link.probe_ports_list()))

    # def generate_deploy(self, commands, service, docker_links):
    #     service = self._get_service_(service)
    #     if not service.deploy.has_value():
    #         return
    #     if not service.config.has_value():
    #         raise DMakeException("You need to specify a 'config' when deploying.")
    #     assert(service.service_name in self.app_package_dirs)
    #     service.deploy.generate_deploy(commands, self.app_name, service.service_name, self.app_package_dirs[service.service_name], docker_links, self.env, service.config)
