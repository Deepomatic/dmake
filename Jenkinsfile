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

        script {
          sh "echo $BUILD_ID"
          if (params.REPO_TO_TEST != 'deepomatic/dmake') {
              BUILD_ID = 0
          }
          sh "echo $BUILD_ID"
        }
      }
    }

    stage('Python 2.x') {
      agent {
          docker {
              reuseNode true
              image "ubuntu:16.04"
              args "-e DMAKE_PAUSE_ON_ERROR_BEFORE_CLEANUP=1 \
                    -e DMAKE_DEBUG=1 \
                    -e REPO=${params.REPO_TO_TEST} \
                    -e BRANCH_NAME=${params.BRANCH_TO_TEST} \
                    -e BUILD_ID=${BUILD_ID}"
          }
      }
      steps {
        sh "apt-get update"
        sh "apt-get install curl g++ python2.7"
        sh "update-alternatives --install /usr/bin/python python /usr/bin/python2.7 1"
        sh "curl https://bootstrap.pypa.io/get-pip.py | python"
        sh "pip install -r requirements.txt"
        script {
          PATH = sh('echo dmake:dmake/utils:$PATH')
        }
        sh('echo $PATH')
        dir('/workspace/workspace') {
          sh "dmake test -d '${params.DMAKE_APP_TO_TEST}'"
          sshagent (credentials: (env.DMAKE_JENKINS_SSH_AGENT_CREDENTIALS ?
                      env.DMAKE_JENKINS_SSH_AGENT_CREDENTIALS : '').tokenize(',')) {
            sh "python --version"
            load 'DMakefile'
          }
        }
      }
    }

    stage('Python 3.x') {
      agent {
          docker {
              reuseNode true
              image 'frolvlad/alpine-python2'
              args '-v ${env.WORKSPACE} /workspace -e PATH=/workspace/dmake:/workspace/dmake/utils'
          }
      }
      steps {
        sh "virtualenv -p python3 workspace/.venv3"
        sh ". workspace/.venv3/bin/activate && pip install -r requirements.txt"
        dir('workspace') {
          sh ". .venv3/bin/activate && dmake test -d '${params.DMAKE_APP_TO_TEST}'"
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
