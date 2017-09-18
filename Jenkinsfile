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
    env.PYTHONPATH = "${env.WORKSPACE}:${env.PYTHONPATH}"
    env.PATH = "${env.WORKSPACE}/deepomatic/dmake:${env.WORKSPACE}/deepomatic/dmake/utils:${env.PATH}"

    // If another repo if targeted, test it as well
    def BRANCH_TO_TEST
    if (params.REPO_TO_TEST == 'deepomatic/dmake') {
        BRANCH_TO_TEST = env.CHANGE_BRANCH ?: env.BRANCH_NAME
    }
    else {
        BRANCH_TO_TEST = params.BRANCH_TO_TEST
        env.BUILD_NUMBER = 0
    }

    stage('Testing') {
        sh ("echo 'Cloning ${BRANCH_TO_TEST} from https://github.com/${params.REPO_TO_TEST}.git'")
        checkout changelog: false,
                 poll: false,
                 scm: [$class: 'GitSCM', branches: [[name: BRANCH_TO_TEST]], doGenerateSubmoduleConfigurations: false,
                 extensions: [[$class: 'WipeWorkspace'],
                              [$class: 'RelativeTargetDirectory', relativeTargetDir: 'workspace'],
                              [$class: 'SubmoduleOption', disableSubmodules: false, parentCredentials: false, recursiveSubmodules: true, reference: '', trackingSubmodules: false],
                              [$class: 'LocalBranch', localBranch: BRANCH_TO_TEST]],
                 submoduleCfg: [], userRemoteConfigs: [[credentialsId: 'dmake-http', url: "https://github.com/${params.REPO_TO_TEST}.git"]]]

        env.DMAKE_ON_BUILD_SERVER=0
        env.REPO=params.REPO_TO_TEST
        env.BRANCH_NAME=""
        env.CHANGE_BRANCH=""
        dir('workspace') {
            sh 'dmake test -d "*"'
        }
    }

}
