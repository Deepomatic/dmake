import dmake.common as common


def entry_point(options):
    common.run_shell_command("docker rm -f `docker ps -q -f name=%s.%s.%s`" % (common.repo, common.branch, common.build_id))
