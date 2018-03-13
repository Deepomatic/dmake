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
            HOME = sh(returnStdout: true, script: 'pwd')
            PATH = sh(returnStdout: true, script: 'echo `pwd`/dmake:`pwd`/dmake/utils:$PATH')
          }
          agent {
              dockerfile {
                  dir 'jenkins/agent'
                  additionalBuildArgs "--build-arg PYTHON_VERSION=2.7 \
                                       --build-arg REPO=${params.REPO_TO_TEST} \
                                       --build-arg BRANCH_NAME=${params.BRANCH_TO_TEST} \
                                       --build-arg BUILD_ID=${BUILD_ID}"
              }
          }
          steps {
            sh "pip install --user -r requirements.txt"
            dir('workspace') {
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
