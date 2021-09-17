properties([
    parameters([
        string(name: 'REPO_TO_TEST',
               defaultValue: 'deepomatic/dmake',
               description: 'The repository to check out.'),
        string(name: 'BRANCH_TO_TEST',
               defaultValue: env.CHANGE_BRANCH ?: env.BRANCH_NAME,
               description: 'The branch to check out. Only used when testing a directory different from deepomatic/dmake.'),
        string(name: 'DEPLOY_BRANCH_TO_TEST',
               defaultValue: env.CHANGE_TARGET ?: 'master',
               description: 'The target branch to use for kubernetes deployment dry-run test.'),
        string(name: 'DMAKE_APP_TO_TEST',
               defaultValue: '*',
               description: 'Application to test. You can also specify a service name if there is no ambiguity. Use * to force the test of all applications.'),
        booleanParam(name: 'DMAKE_WITH_DEPENDENCIES',
                     defaultValue: true,
                     description: 'Also execute with service dependencies if checked'),
        string(name: 'DMAKE_COMMAND',
               defaultValue: 'test',
               description: 'dmake command to execute'),
        booleanParam(name: 'DMAKE_SKIP_TESTS',
                     defaultValue: false,
                     description: 'Skip tests if checked'),
        booleanParam(name: 'DMAKE_DEBUG',
                     defaultValue: true,
                     description: 'Enable dmake debug logs'),
        booleanParam(name: 'DMAKE_PAUSE_ON_ERROR_BEFORE_CLEANUP',
                     defaultValue: true,
                     description: 'Ask user confirmation before DMake cleanup.'),
        booleanParam(name: 'DMAKE_FORCE_BASE_IMAGE_BUILD',
                     defaultValue: false,
                     description: 'Force base image build (don\'t use base image cache)'),
        string(name: 'CUSTOM_ENVIRONMENT',
               defaultValue: '',
               description: '(optional) Custom environment variables, for custom build. Example: \'FOO=1 BAR=2\''),
        booleanParam(name: 'ABORT_OLD_BUILDS_ON_PR',
                     defaultValue: true,
                     description: 'Abort old builds when job is for a PR.'),
    ]),
    pipelineTriggers([])
])

// Abort old builds for PRs
// from https://issues.jenkins.io/browse/JENKINS-43353?focusedCommentId=395851&page=com.atlassian.jira.plugin.system.issuetabpanels:comment-tabpanel#comment-395851
def is_pr = !!env.CHANGE_BRANCH  // For PRs Jenkins will give the source branch name
if (is_pr && params.ABORT_OLD_BUILDS_ON_PR) {
  def buildNumber = env.BUILD_NUMBER as int
  if (buildNumber > 1) milestone(buildNumber - 1)
  milestone ordinal: buildNumber, label: 'Abort old builds'
}

node {
  def self_test = (params.REPO_TO_TEST == 'deepomatic/dmake')

  def dmake_with_dependencies = params.DMAKE_WITH_DEPENDENCIES ? '--dependencies' : '--standalone'

  stage('Setup') {
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
    env.PATH = "${env.WORKSPACE}/dmake:${env.WORKSPACE}/dmake/utils:${env.PATH}"

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

    // Setup environment variables as Jenkins would do
    env.REPO=params.REPO_TO_TEST
    env.BRANCH_NAME=params.BRANCH_TO_TEST
    if (!self_test) {
        env.BUILD_ID = 0
    }
    env.CHANGE_BRANCH=""
    env.CHANGE_TARGET=""
    env.CHANGE_ID=""
    // params are automatically exposed as environment variables
    // but booleans to string generates "true"
    if (params.DMAKE_DEBUG) {
        env.DMAKE_DEBUG=1
    }
    if (params.DMAKE_PAUSE_ON_ERROR_BEFORE_CLEANUP) {
        env.DMAKE_PAUSE_ON_ERROR_BEFORE_CLEANUP=1
    }

    // test parallel execution
    env.DMAKE_PARALLEL_EXECUTION = 1
  }
  stage('Python 3.x') {
    sh "virtualenv -p python3 workspace/.venv3"
    sh ". workspace/.venv3/bin/activate && pip3 install -r requirements.dev.txt"
    sh "rm workspace/.venv3/bin/python" // remove python to detect illegitime usage of python (which is often python2)
    dir('workspace') {
      if (self_test) {
        try {
          sh ". .venv3/bin/activate && pytest -vv --color=yes --junit-xml=junit.xml --junit-prefix=python3 --cov=dmake/ --cov-report=xml:coverage.xml --cov-report html:cover/"
        } finally {
          junit keepLongStdio: true, testResults: 'junit.xml'
          step([$class: 'CoberturaPublisher', autoUpdateHealth: false, autoUpdateStability: false, coberturaReportFile: 'coverage.xml', failUnhealthy: false, failUnstable: false, maxNumberOfBuilds: 0, onlyStable: false, sourceEncoding: 'ASCII', zoomCoverageChart: false])
          publishCoverage adapters: [coberturaAdapter(mergeToOneReport: true, path: 'coverage.xml')], calculateDiffForChangeRequests: true, sourceFileResolver: sourceFiles('NEVER_STORE')
          publishHTML(target: [allowMissing: false, alwaysLinkToLastBuild: false, keepAll: true, reportDir: 'cover', reportFiles: 'index.html', reportName: 'dmake HTML coverage report'])
        }
      }
      SECRET_FILE_PATH = sh (
        script: 'mktemp',
        returnStdout: true
      ).trim()
      sh "echo this_is_a_secret_value > ${SECRET_FILE_PATH}"
      if (params.DMAKE_COMMAND == 'test') {
        echo "First: kubernetes deploy dry-run (just plan deployment on target branch to validate kubernetes manifests templates)"
        withEnv([" KUBECONFIG=${MINIKUBE_HOME}/kubeconfig", "DMAKE_TEST_K8S_NAMESPACE=dmake-test"]) {
          sh "kubectl create namespace ${env.DMAKE_TEST_K8S_NAMESPACE} --save-config --dry-run=client -o yaml | kubectl apply -f -"
          sh "kubectl create namespace ${env.DMAKE_TEST_K8S_NAMESPACE}-2 --save-config --dry-run=client -o yaml | kubectl apply -f -"
          sh ". .venv3/bin/activate && ${params.CUSTOM_ENVIRONMENT} SECRET_FILE_PATH=${SECRET_FILE_PATH} DMAKE_SKIP_TESTS=1 dmake deploy ${dmake_with_dependencies} '${params.DMAKE_APP_TO_TEST}' --branch ${params.DEPLOY_BRANCH_TO_TEST}"
          // skip execution: just plan
        }
        echo "Kubernetes deploy dry-run finished in success!"
      }
      echo "Now really running dmake"
      sh ". .venv3/bin/activate && ${params.CUSTOM_ENVIRONMENT} SECRET_FILE_PATH=${SECRET_FILE_PATH} dmake ${params.DMAKE_COMMAND} ${dmake_with_dependencies} '${params.DMAKE_APP_TO_TEST}'"
      sshagent (credentials: (env.DMAKE_JENKINS_SSH_AGENT_CREDENTIALS ?
                  env.DMAKE_JENKINS_SSH_AGENT_CREDENTIALS : '').tokenize(',')) {
        load 'DMakefile'
      }
    }
  }
}
