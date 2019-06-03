package com.deepo;

/*
* This file contains the API functions that can be imported and called
* by a jenkins file
*/

// TODO: Find a better way to include other files functions
class Utils {
   static build = new com.deepo.Build();
   static slack = new com.deepo.Slack();
}

def boolToInt(value) {
   return value ? 1 : 0
}

// Generic weapper to dmake passing the proper arguments
def dmake_call(String dmake_command, String dmake_with_dependencies, String dmake_app, environment = []){
    sshagent (credentials: (env.DMAKE_JENKINS_SSH_AGENT_CREDENTIALS ?
                            env.DMAKE_JENKINS_SSH_AGENT_CREDENTIALS : '').tokenize(',')) {
        if (environment.empty){
            // Unfortunatlly withEnv does not accept an empty list
            environment = ['empty=null']
        }
        checkout([$class: 'GitSCM',
                  branches: scm.branches,
                  extensions: scm.extensions + [[$class: 'SubmoduleOption', recursiveSubmodules: true]],
                  userRemoteConfigs: scm.userRemoteConfigs])
        withEnv(environment){
            sh "python3 \$(which dmake) ${dmake_command} ${dmake_with_dependencies} ${dmake_app}"
            load 'DMakefile'
        }
    }
}

// Function that takes the parameters and creates a build dmake call
def execute(project_name, dmake_app_list, use_gpu = true) {

    // TODO: I have not found ways to load it automatically, but maybe we can remove this call.
    // Infact probably it will work only in single node builds.
    Utils.build.setup_pipeline_parameters()

    def dmake_command = params.DMAKE_COMMAND
    try {
        dmake_command = OVERRIDE_DMAKE_COMMAND
    } catch (e) {}

    if (! dmake_command) {
        dmake_command = Utils.build.isPR() ? 'test' : 'deploy'
    }

    def dmake_with_dependencies = params.DMAKE_WITH_DEPENDENCIES ? '' : '--standalone'

    if (! dmake_app_list) {
        make_app_list = [params.DMAKE_APP]
    }

    if (use_gpu) {
        use_gpu = ! Utils.build.spareGPU()
    }
    def environment = [params.CUSTOM_ENVIRONMENT]
    // FIXME: addAll does not work if environment is empty
    environment = ["ALLOW_NO_GPU=${boolToInt(use_gpu)}",
                   "DMAKE_NO_GPU=${boolToInt(use_gpu)}",
                   "VULCAN_MINIKUBE_CONTEXT=${env.MINIKUBE_CONTEXT}"]
    sh "echo ${environment}"
    def buildMessage = null
    try {
        // FIXME: This lines can be here or i need to put them in the ssh?
        if (params.CLEAR_WORKSPACE) {
            deleteDir()
        }
        for (dmake_app in dmake_app_list) {
            dmake_call(dmake_command, dmake_with_dependencies, dmake_app, environment)
        }
        currentBuild.result = 'SUCCESS'
    } catch (e) {
        def abortedCauseDescription = Utils.build.getCauseDescriptionIfAborted()
        if (abortedCauseDescription) {
            currentBuild.result = 'ABORTED'
            buildMessage = abortedCauseDescription
        } else {
            currentBuild.result = 'FAILURE'
        }
        throw e
    } finally {
        if (Utils.slack.shouldNotifyResult()) {
            Utils.slack.notifyBuild(project_name, currentBuild.result, buildMessage)
        }
    }
}
