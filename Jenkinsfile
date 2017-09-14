properties([
    parameters([
        string(name: 'REPO_TO_TEST',
               defaultValue: 'deepomatic/dmake',
               description: 'The repository to check.'),
        string(name: 'BRANCH_TO_TEST',
               defaultValue: 'master',
               description: 'The branch to check.')
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

    // Run tests of dmake
    load "${DMAKE_JENKINS_FILE}_core"

    // If another repo if targeted, test it as well
    env.REPO_TO_TEST = params.REPO_TO_TEST
    env.BRANCH_TO_TEST = params.BRANCH_TO_TEST
    stage('Thrid-party test') {
        if (env.REPO_TO_TEST != '') {
            checkout changelog: false,
                     poll: false,
                     scm: [$class: 'GitSCM', branches: [[name: '*/master']], doGenerateSubmoduleConfigurations: false,
                     extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'workspace'],
                                  [$class: 'SubmoduleOption', disableSubmodules: false, parentCredentials: false, recursiveSubmodules: true, reference: '', trackingSubmodules: false],
                                  [$class: 'LocalBranch', localBranch: '${BRANCH_TO_TEST}']],
                     submoduleCfg: [], userRemoteConfigs: [[credentialsId: 'dmake-http', url: 'https://github.com/${REPO_TO_TEST}.git']]]


            withEnv([
                    'DMAKE_ON_BUILD_SERVER=0',
                    'REPO=${REPO_TO_TEST}',
                    'BRANCH_NAME=',
                    'BUILD_NUMBER=0']) {
                dir('workspace') {
                    sh 'dmake test -d "*"'
                }
            }
        }
    }

}
