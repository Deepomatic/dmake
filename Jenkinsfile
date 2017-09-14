properties([
    parameters([
        string(name: 'REPO_TO_TEST',
               defaultValue: 'deepomatic/dmake',
               description: 'The repository to check out.'),
        string(name: 'BRANCH_TO_TEST',
               defaultValue: 'master',
               description: 'The branch to check out. Only used when testing a directory different from deepomatic/dmake.')
    ]),
    pipelineTriggers([])
])


node {
    checkout scm
    try {
        sh 'git submodule update --init'
    } catch(error) {
        deleteDir()
        checkout scm
        sh 'git submodule update --init'
    }

    // Use this version of dmake
    env.PYTHONPATH = pwd()
    env.PATH = "${PYTHONPATH}:${PYTHONPATH}/deepomatic/dmake/utils:$PATH"

    // If another repo if targeted, test it as well
    env.REPO_TO_TEST = params.REPO_TO_TEST
    if (params.REPO_TO_TEST == 'deepomatic/dmake') {
        env.BRANCH_TO_TEST = env.CHANGE_BRANCH
    }
    else {
        env.BRANCH_TO_TEST = params.BRANCH_TO_TEST
        env.BUILD_NUMBER = 0
    }

    stage('Thrid-party test') {
        sh ('echo "Cloning ${BRANCH_TO_TEST} from https://github.com/${REPO_TO_TEST}.git"')
        checkout changelog: false,
                 poll: false,
                 scm: [$class: 'GitSCM', branches: [[name: env.BRANCH_TO_TEST]], doGenerateSubmoduleConfigurations: false,
                 extensions: [[$class: 'WipeWorkspace'],
                              [$class: 'RelativeTargetDirectory', relativeTargetDir: 'workspace'],
                              [$class: 'SubmoduleOption', disableSubmodules: false, parentCredentials: false, recursiveSubmodules: true, reference: '', trackingSubmodules: false],
                              [$class: 'LocalBranch', localBranch: env.BRANCH_TO_TEST]],
                 submoduleCfg: [], userRemoteConfigs: [[credentialsId: 'dmake-http', url: 'https://github.com/${REPO_TO_TEST}.git']]]

        env.DMAKE_ON_BUILD_SERVER=0
        env.REPO=env.REPO_TO_TEST
        env.CHANGE_BRANCH=""
        dir('workspace') {
            sh 'dmake test -d "*"'
        }
    }

}
