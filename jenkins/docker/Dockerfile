FROM jenkins:2.19.3
MAINTAINER Vincent Delaitre <vincent@deepomatic.com>

USER root

# Install libs
RUN apt-get update && apt-get --no-install-recommends -y install python-pip python3-pip

# Install docker client
RUN cd /tmp && wget -O docker.tgz https://get.docker.com/builds/Linux/x86_64/docker-1.12.2.tgz && tar -zxvf docker.tgz && cp docker/docker /usr/local/bin/ && rm -rf /tmp/*

# Install sudo to switch user
RUN apt-get install -y sudo && usermod -a -G sudo jenkins && echo "jenkins ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Setup DMake variables
ENV DMAKE_PATH              /dmake
ENV DMAKE_JENKINS_FILE      $DMAKE_PATH/dmake/templates/jenkins/Jenkinsfile
ENV DMAKE_ON_BUILD_SERVER   1
ENV DMAKE_SSH_KEY           ""
ENV DMAKE_CONFIG_DIR        ""

# Clone DMake
RUN git clone https://github.com/Deepomatic/dmake.git $DMAKE_PATH && pip install -r $DMAKE_PATH/requirements.txt

# Add DMake to path
ENV PATH                  $PATH:$DMAKE_PATH/dmake:$DMAKE_PATH/dmake/utils
ENV PYTHONPATH            $PYTHONPATH:$DMAKE_PATH

# Import local docker sockets for jenkins
COPY ./wrap_docker /wrap_docker

ENTRYPOINT ["/wrap_docker"]
CMD ["/usr/local/bin/jenkins.sh"]
