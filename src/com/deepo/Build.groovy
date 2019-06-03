package com.deepo;

/*
* File containing all the build related utilities
*/

def isPR() {
    // For PRs Jenkins will give the source branch name
    return !!env.CHANGE_BRANCH
}

// Returns true if the gpu should be spared in this build otherwise false
def spareGPU() {
    if (env.BRANCH_NAME == "release") {
       return false
    }
    if (env.BRANCH_NAME == "master") {
       return false
    }
    return true
}

// Utility function that returns the jenkins interruption cause
@NonCPS
def getCauseDescriptionIfAborted() {
    def action = manager.build.getAction(InterruptedBuildAction.class)
    if (action) {
        for (cause in action.causes) {
            if (cause instanceof jenkins.model.CauseOfInterruption.UserInterruption) {
                return cause.getShortDescription()
            }
        }
    }
}

def setup_pipeline_parameters() {

    // default parameters from dmake user repository
    try {
        default_dmake_app=DEFAULT_DMAKE_APP
    } catch (e) {
        default_dmake_app='*'
    }

    try {
        default_dmake_with_dependencies=DEFAULT_DMAKE_WITH_DEPENDENCIES
    } catch (e) {
        default_dmake_with_dependencies=true
    }

    try {
        default_dmake_command=DEFAULT_DMAKE_COMMAND
    } catch (e) {
        default_dmake_command=''
    }

    try {
        default_dmake_skip_tests=DEFAULT_DMAKE_SKIP_TESTS
    } catch (e) {
        default_dmake_skip_tests=false
    }

    try {
        default_dmake_debug=DEFAULT_DMAKE_DEBUG
    } catch (e) {
        default_dmake_debug=false
    }

    try {
        default_dmake_pause_on_error_before_cleanup=DEFAULT_PAUSE_ON_ERROR_BEFORE_CLEANUP
    } catch (e) {
        default_dmake_pause_on_error_before_cleanup=false
    }

    try {
        default_dmake_force_base_image_build=DEFAULT_DMAKE_FORCE_BASE_IMAGE_BUILD
    } catch (e) {
        default_dmake_force_base_image_build=false
    }

    try {
        default_custom_environment=DEFAULT_CUSTOM_ENVIRONMENT
    } catch (e) {
        default_custom_environment=''
    }

    try {
        default_clear_workspace=DEFAULT_CLEAR_WORKSPACE
    } catch (e) {
        default_clear_workspace=false
    }

    try {
        default_pipeline_triggers=DEFAULT_PIPELINE_TRIGGERS
    } catch (e) {
        default_pipeline_triggers=[]
    }

    properties([
        parameters([
            string(name: 'DMAKE_APP',
                   defaultValue: default_dmake_app,
                   description: '(optional) Application to work on (deploy/test/...). You can also specify a service name if there is no ambiguity. Use * to force the deployment of all applications. Leave empty for default behaviour.'),
            booleanParam(name: 'DMAKE_WITH_DEPENDENCIES',
                   defaultValue: default_dmake_with_dependencies,
                   description: 'Also execute with service dependencies if checked'),
            string(name: 'DMAKE_COMMAND',
                   defaultValue: default_dmake_command,
                   description: '(optional) dmake command to execute. Default: `test` for PR jobs, `deploy` otherwise'),
            booleanParam(name: 'DMAKE_SKIP_TESTS',
                   defaultValue: default_dmake_skip_tests,
                   description: 'Skip tests if checked'),
            booleanParam(name: 'DMAKE_DEBUG',
                   defaultValue: default_dmake_debug,
                   description: 'Enable dmake debug logs'),
            booleanParam(name: 'DMAKE_PAUSE_ON_ERROR_BEFORE_CLEANUP',
                   defaultValue: default_dmake_pause_on_error_before_cleanup,
                   description: 'Ask user confirmation before DMake cleanup.'),
            booleanParam(name: 'DMAKE_FORCE_BASE_IMAGE_BUILD',
                   defaultValue: default_dmake_force_base_image_build,
                   description: 'Force base image build (don\'t use base image cache)'),
            string(name: 'CUSTOM_ENVIRONMENT',
                   defaultValue: default_custom_environment,
                   description: '(optional) Custom environment variables, for custom build. Example: \'FOO=1 BAR=2\''),
            booleanParam(name: 'CLEAR_WORKSPACE',
                   defaultValue: default_clear_workspace,
                   description: 'Wipe out the workspace when starting the build if checked'),
        ]),
        pipelineTriggers(default_pipeline_triggers)
    ])

    // params are automatically exposed as environment variables
    // but booleans to string generates "true"
    if (params.DMAKE_DEBUG) {
        env.DMAKE_DEBUG=1
    }
    if (params.DMAKE_PAUSE_ON_ERROR_BEFORE_CLEANUP) {
        env.DMAKE_PAUSE_ON_ERROR_BEFORE_CLEANUP=1
    }
}
