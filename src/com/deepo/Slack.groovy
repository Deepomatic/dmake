package com.deepo;

/*
* File containing slack integration functions
*/

// Slack integration method
def notifyBuild(String channel, String buildStatus, String buildMessage) {
    if (buildStatus == 'SUCCESS') {
        color = '#36A64F' // green
    } else if (buildStatus == 'ABORTED') {
        color = '#ABABAB' // grey
    } else {
        color = '#D00000' // red
    }
    def message = "${buildStatus}"
    if (buildMessage) {
        message += " (${buildMessage})"
    }
    message += ": Job '${env.JOB_NAME} [${env.BUILD_NUMBER}]' (${env.BUILD_URL})"
    slackSend (color: color, message: message, botUser: true, channel: channel)
}

// Returns true if a notification should be returned otherwise false
def shouldNotifyResult() {
    return  (env.BRANCH_NAME == "release" || env.BRANCH_NAME == "master") ? 1 : 0
}
