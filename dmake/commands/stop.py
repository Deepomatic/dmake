import dmake.common as common


def entry_point(options):
    common.logger.info('Stopping all containers for current repo and branch.')
    common.run_shell_command('CONTAINER_IDS=$(docker ps -q -f name=%s.%s.%s); test -n "${CONTAINER_IDS}" && docker rm -f ${CONTAINER_IDS}' % (common.repo, common.branch, common.build_id))
