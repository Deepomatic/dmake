properties([
    parameters([
        string(name: 'REPO_TO_TEST',
               defaultValue: 'deepomatic/dmake',
               description: 'The repository to check out.'),
        string(name: 'BRANCH_TO_TEST',
               defaultValue: env.CHANGE_BRANCH ?: env.BRANCH_NAME,
               description: 'The branch to check out. Only used when testing a directory different from deepomatic/dmake.'),
        string(name: 'DMAKE_APP_TO_TEST',
               defaultValue: '*',
               description: 'Application to test. You can also specify a service name if there is no ambiguity. Use * to force the test of all applications.'),
        booleanParam(name: 'DMAKE_SKIP_TESTS',
                     defaultValue: false,
                     description: 'Skip tests if checked')
    ]),
    pipelineTriggers([])
])

pipeline {
  agent any

  stages {
    stage('Setup') {
      steps {
        checkout scm

        // Clone repo to test
        sh ("echo 'Cloning ${params.BRANCH_TO_TEST} from https://github.com/${params.REPO_TO_TEST}.git'")
            checkout changelog: false,
                     poll: false,
                     scm: [$class: 'GitSCM', branches: [[name: params.BRANCH_TO_TEST]], doGenerateSubmoduleConfigurations: false,
                     extensions: [[$class: 'WipeWorkspace'],
                                  [$class: 'RelativeTargetDirectory', relativeTargetDir: 'workspace'],
                                  [$class: 'SubmoduleOption', disableSubmodules: false, parentCredentials: false, recursiveSubmodules: true, reference: '', trackingSubmodules: false],
                                  [$class: 'LocalBranch', localBranch: params.BRANCH_TO_TEST]],
                     submoduleCfg: [], userRemoteConfigs: [[credentialsId: 'dmake-http', url: "https://github.com/${params.REPO_TO_TEST}.git"]]]
      }
    }

    stage('Run Tests') {
      parallel {
        stage('Python 2.x') {
          environment {
            PATH = "PATH=${env.WORKSPACE}/dmake:${env.WORKSPACE}/dmake/utils:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
          }
          agent {
              docker {
                  image 'deepomatic/ubuntu:16.04-python2.7'
                  args  '-e REPO=${params.REPO_TO_TEST} \
                         -e BRANCH_NAME=${params.BRANCH_NAME} \
                         -e BUILD_ID=${params.BUILD_ID} \
                         -e DMAKE_PAUSE_ON_ERROR_BEFORE_CLEANUP=${params.DMAKE_PAUSE_ON_ERROR_BEFORE_CLEANUP} \
                         -e DMAKE_DEBUG=${params.DMAKE_DEBUG} \
                         -e HOME=. \
                         -v /var/run/docker.sock:/var/run/docker.sock \
                         -v /usr/bin/docker:/usr/bin/docker'
              }
          }
          steps {
            echo "PATH is: $PATH"
            sh "pip install --user -r requirements.txt"
            dir('workspace') {
              sh "ls ../dmake"
              sh "dmake test -d '${params.DMAKE_APP_TO_TEST}'"
              sshagent (credentials: (env.DMAKE_JENKINS_SSH_AGENT_CREDENTIALS ?
                          env.DMAKE_JENKINS_SSH_AGENT_CREDENTIALS : '').tokenize(',')) {
                sh "python --version"
                load 'DMakefile'
              }
            }
          }
        }
      }
    }
  }
}
