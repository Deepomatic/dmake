properties([
    parameters([
        string(name: 'REPO_TO_TEST',
               defaultValue: 'vulcain',
               description: 'The repository to check.'),
        string(name: 'BRANCH_TO_TEST',
               defaultValue: 'stag',
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

    checkout changelog: false,
             poll: false,
             scm: [$class: 'GitSCM', branches: [[name: '*/master']], doGenerateSubmoduleConfigurations: false,
             extensions: [[$class: 'RelativeTargetDirectory', relativeTargetDir: 'workspace'],
                          [$class: 'SubmoduleOption', disableSubmodules: false, parentCredentials: false, recursiveSubmodules: true, reference: '', trackingSubmodules: false],
                          [$class: 'LocalBranch', localBranch: '${BRANCH_TO_TEST}']],
             submoduleCfg: [], userRemoteConfigs: [[credentialsId: 'dmake-http', url: 'https://github.com/Deepomatic/${REPO_TO_TEST}.git']]]


    withEnv([
            'DMAKE_ON_BUILD_SERVER=0',
            'REPO=${REPO_TO_TEST}',
            'BRANCH_NAME=',
            'BUILD_NUMBER=0']) {
        env.PYTHONPATH = pwd()
        env.PATH = "${PYTHONPATH}:${PYTHONPATH}/deepomatic/dmake/utils:$PATH"
        dir('workspace') {
            sh('env')
            sh 'dmake test "*"'
        }
    }

}
