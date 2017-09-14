# DMake v0.1

**DMake** is a tool to manage micro-service based applications. It allows to easily build, run, test and deploy an entire application or one of its micro-services.

Table of content:
- [Installation](#installation)
- [Tutorial](#tutorial)
- [Using DMake with Jenkins](#using-dmake-with-jenkins)
- [Configuring Docker](#configuring-docker)
- [Documentation](#documentation)
- [Example](#example)

## Installation

In order to run **DMake**, you will need:
- Python 2.7 or newer
- Docker 1.12 or newer

In order to install **DMake**, use the following:

```
$ git clone https://github.com/Deepomatic/dmake.git
$ cd dmake
$ ./install.sh
```

After following instructions of ```install.sh```, check that **DMake** is found by running:

```
$ dmake
```

It should display the help message with the list of commands.

## Tutorial

To start the tutorial, enter the tutorial directory:

```
$ cd tutorial
```

For those who just want to see the results, just run:

```
$ dmake run web -d
```

Once it has completed, the factorial demo is available at [http://localhost:8000](http://localhost:8000)

Before moving to the details, do not forget to shutdown the launched containers with:

```
$ dmake stop dmake-tutorial
```

Alright ! To simulate an application made of several micro-services, this project is made of two services:
- a Django app that shows a form where you enter a number '*n*', in the ```web/``` directory.
- a worker that computes factorial '*n*', in the ```worker/``` directory.

**DMake** allows you to specify how your whole app should be tested and run by relying on ```dmake.yml``` files. **DMake** searches for the whole repository and parses all those files. In this project, there is two of them in each of the ```web/``` and ```worker/``` directories.

Let's start with the **DMake** configuration of the worker that computes the factorial by having a look at ```worker/dmake.yml```.

The two first lines indicate the version of **DMake** that will parse the YAML file and the name of your app:

```yaml
dmake_version: 0.1
app_name: dmake-tutorial
```

The ```app_name``` is used to group the multiple services of an app together, allowing **DMake** to separately process several apps in the same directory.

Then comes the specification of the Docker environment in which your app will run:

```yaml
docker:
    root_image:
        name: ubuntu
        tag: 16.04
    base_image:
        name: dmake-tutorial-worker-base
        install_scripts:
            - deploy/dependencies.sh
```

This states that your app runs on Ubuntu 16.04. It will also install and build all the dependencies as specified in ```deploy/dependencies.sh``` and commit a Docker image named ```dmake-tutorial-worker-base``` to avoid building it each time you run **DMake**. If you indicate a user name for the base Docker image (e.g. if we had put ```deepomatic/dmake-tutorial-worker-base```), it will push the image on Docker Hub to share it with all your collaborators.

We then declare the environment variables:
```yaml
env:
    branches:
        master:
            ENV_TYPE: prod
            AMQP_URL: amqp://1.2.3.4/prod
    default:
        ENV_TYPE: dev
        AMQP_URL: amqp:///192.168.1.45/dev
```

You can have default environment variables (usually  for development purposes) and variables specific to a branch (used when deploying our app), in which case the default value of the variable is overriden.

The next thing to declare are the "standard" services that you will need. They are shared across the whole application (so no need to re-declare them in another ```dmake.yml``` file with the same ```app_name```):

```yaml
docker_links:
    - image_name: rabbitmq:3.6
      link_name: rabbitmq
      testing_options: -e RABBITMQ_DEFAULT_USER=user -e RABBITMQ_DEFAULT_PASS=password -e RABBITMQ_DEFAULT_VHOST=dev
```

This declares that we will use RabbitMQ 3.6 (Docker image ```rabbitmq:3.6```) and that we will refer to it as the ```rabbitmq``` service. This service will be made available to your app by linking it to its Docker container. You can specify Docker options to add when launching the Docker image with ```testing_options```.

Then comes the commands to build the services declared in this file (see below) and there unit-tests.

```yaml
build:
    commands:
        - make
```

Last but not least, we have the list of all the  micro-services declared in this file. Here there is only one micro service named ```worker```:

```yaml
services:
    -
        service_name: worker
        config:
            docker_image:
                entrypoint: deploy/entrypoint.sh
                start_script: deploy/start.sh
        tests:
            docker_links_names:
                - rabbitmq
            commands:
                - ./bin/worker_test
```

**DMake** builds a Docker image for each specified service. The field ```docker_image``` allows to configure this Docker image. The ```start_script``` field specifies the default command that should be run when starting Docker container. The ```test``` field states that **DMake** needs to launch the compiled file ```./bin/worker_test``` and link with the RabbitMQ service defined previously by ```docker_links```.

Speaking about linking, we use the entry point script ```deploy/entrypoint.sh``` (as defined by the field ```entrypoint```) to override the environment variable ```AMQP_URL``` with the URL of the linked RabbitMQ container. Check out [this page](https://docs.docker.com/engine/userguide/networking/default_network/container-communication/) to know more about linking Docker containers.

Now that we went through the configuration file, you can try to test the worker with:

```
$ dmake test worker
```

You can also run a shell session within the base Docker image:

```
$ dmake shell -d worker
```

The ```-d``` option tells **DMake** to run all the dependencies of the service as well. In this case, it runs RabbitMQ and the specified entry point sets the ```AMQP_URL``` environment variable to point to this local RabbitMQ server. If you do not specify the ```-d```, it will run the container as a stand-alone and it will try to connect to the RabbitMQ server specified in the ```env``` field (i.e. with the URL ```amqp://1.2.3.4/prod```)

Let's now look at the other configuration file ```web/dmake.yml```. It pretty much looks the same. The only few things which differs are:
- The ```python_requirements``` field to specify the python libraries to install. They are installed with ```pip``` (which is installed automatically) after the ```install_scripts```.
- The ```needed_services``` field which say that the Django API needs its worker to be fully functional.
- The ```ports``` field which stats which ports of the Docker container needs to be exposed.

You can now run the full app with:

```
$ dmake run -d web
```

Once it has completed, the factorial demo is available at [http://localhost:8000](http://localhost:8000)

If you paid attention, this is not the same command as the one at the beginning of this section. Here you run the ```web``` service with all the dependencies (the worker and RabbitMQ). If you specify the application name (like the command at the beginning of this section) it automatically runs all the dependencies as well.

By the way, when there are multiple application in the same repository and multiple services with the same name, you must specify the full service name like this:

```
$ dmake run -d dmake-tutorial/web
```

## Using DMake with Jenkins

Jenkins is an automation server to build an deploy your applications. In order to test it, just do:

```
$ cd jenkins
$ make
```

It will build a Docker image for Jenkins (cf ```jenkins/docker/Dockerfile```) and launch it locally. Once launched, you can access it on [http://localhost:8080/](http://localhost:8080/) and connect with user ```admin``` and password ```password```. You will see a job called ```dmake-tutorial```. You can trigger a build of this job by clicking on the "play" button on the right and look at the build's output on [http://localhost:8080/job/dmake-tutorial/job/master/lastBuild/console](http://localhost:8080/job/dmake-tutorial/job/master/lastBuild/console).

In order to setup DMake in your own Jenkins server, you can adjust the Dockerfile in ```jenkins/docker/Dockerfile``` to your taste.

## Configuring Docker

When experiencing with DMake (either on your own machine or on Jenkins), you may notice that files produced when building your app belong to the root user.

You may check if this is the case on your machine by running ```docker run -v `pwd`:/mnt -ti ubuntu touch /mnt/foobar && ls -l foobar && rm foobar```. If the resulting owner of the file is root, you might need to adapt the configuration of Docker as indicated below.

One simple solution would be to perform a ```sudo chown $(id -u):$(id -g) -R .``` after each build. This is however not very convenient nor suitable.

Another solution consists of configuring Docker to map your user on the host machine to the root user of containers. In the following we assume the default non root user of the machine is ```deepomatic``` with UID 1000 and GID 1000. You simply need to:
- ensure that the file ```/etc/subuid``` (respectively ```/etc/subgid```) contains a line like ```deepomatic:1000:65536``` where 1000 stands for your UID (respectively GID).
- Edit the file ```/etc/default/docker``` so that it contains the following line:
```bash
DOCKER_OPTS="-g /mnt/docker --userns-remap=ubuntu"
```
- Restart Docker: ```sudo restart docker```
- If you use the provided Jenkins image, change the Docker socket ownership to your user: e.g. ```sudo chown deepomatic /var/run/docker.sock```. This will allow Jenkins to interact with Docker within its container. You need to do this each time you start Jenkins so you might want to include this into Jenkins start script.

This poses another problem when you try to use the Dockerfile provided in this repository for Jenkins: ```jenkins/docker/Dockerfile```. As a user called ```jenkins``` is declared in the original Jenkins Dockerfile, Jenkins won't start because all the file in the container belong to root and not to the ```jenkins``` user. In order to set the ownership to ```jenkins``` (with a UID of 1000 and GID 1000) in the container, the files need to have a UID and GID of 2000 on the host machine (or 1000+x if x is the UID/GID of your user). See [Docker Documentation](https://docs.docker.com/engine/reference/commandline/dockerd/#/daemon-user-namespace-options).

A convenient way to achieve this is to create a new ```jenkins``` user on our machine with the correct UID and GID:

```
$ groupadd -g 2000 jenkins
$ useradd -u 2000 -g 2000 -d ${DMAKE_PATH}/jenkins/jenkins_home -s /bin/bash jenkins
$ chown jenkins:jenkins -R ${DMAKE_PATH}/jenkins/jenkins_home
```

## Documentation

This Documentation was generated automatically.

- **dmake_version** *(string)*: The dmake version.
- **app_name** *(string)*: The application name.
- **blacklist** *(array\<file path\>, default = [])*: List of dmake files to blacklist.
- **env** *(mixed)*: Environment variables to embed in built docker images. It can be one of the followings:
    - a file path
    - an object with the following fields:
        - **default** *(object, optional)*: List of environment variables that will be set by default. It must be an object with the following fields:
            - **source** *(string)*: Source a bash file which defines the environment variables before evaluating the strings of environment variables passed in the *variables* field.
            - **variables** *(free style object, default = {})*: Defines environment variables used for the services declared in this file. You might use pre-defined environment variables (or variables sourced from the file defined in the *source* field).
        - **branches** *(free style object, default = {})*: If the branch matches one of the following fields, those variables will be defined as well, eventually replacing the default.
            - **source** *(string)*: Source a bash file which defines the environment variables before evaluating the strings of environment variables passed in the *variables* field.
            - **variables** *(free style object, default = {})*: Defines environment variables used for the services declared in this file. You might use pre-defined environment variables (or variables sourced from the file defined in the *source* field).
- **docker** *(mixed)*: The environment in which to build and deploy. It can be one of the followings:
    - a file path to another dmake file (which will be added to dependencies) that declares a docker field, in which case it replaces this file's docker field.
    - an object with the following fields:
        - **root_image** *(mixed)*: The source image name to build on. It can be one of the followings:
            - a file path to another dmake file, in which base the root_image will be this file's base_image.
            - an object with the following fields:
                - **name** *(string)*: Root image name.
                - **tag** *(string)*: Root image tag (you can use environment variables).
        - **base_image** *(object, optional)*: Base (intermediate) image to speed-up builds. It must be an object with the following fields:
            - **name** *(string)*: Base image name. If no docker user is indicated, the image will be kept locally.
            - **version** *(string, default = latest
...)*: Base image version. The branch name will be prefixed to form the docker image tag.
            - **install_scripts** *(array\<file path\>, default = [])*:
            - **python_requirements** *(file path, default = '')*: Path to python requirements.txt.
            - **python3_requirements** *(file path, default = '')*: Path to python requirements.txt.
            - **copy_files** *(array\<file path\>, default = [])*: Files to copy. Will be copied before scripts are ran. Paths need to be sub-paths to the build file to preserve MD5 sum-checking (which is used to decide if we need to re-build docker base image). A file 'foo/bar' will be copied in '/base/user/foo/bar'.
        - **mount_point** *(string, default = /app)*: Mount point of the app in the built docker image. Needs to be an absolute path.
        - **command** *(string, default = bash
...)*: Only used when running 'dmake shell': set the command of the container.
- **docker_links** *(array\<object\>, default = [])*: List of link to create, they are shared across the whole application, so potentially across multiple dmake files.
    - **image_name** *(string)*: Name and tag of the image to launch.
    - **link_name** *(string)*: Link name.
    - **volumes** *(array\<string>\, default = [])*: For the 'shell' command only. The list of volumes to mount on the link. It must be in the form ./host/path:/absolute/container/path. Host path is relative to the dmake file.
    - **testing_options** *(string, default = '')*: Additional Docker options when testing on Jenkins.
- **build** *(object, optional)*: Commands to run for building the application. It must be an object with the following fields:
    - **env** *(object, optional)*: Environment variable to define when building. It must be an object with the following fields:
        - **testing** *(free style object, default = {})*: List of environment variables that will be set when building for testing.
        - **production** *(free style object, default = {})*: List of environment variables that will be set when building for production.
    - **commands** *(array\<object\>, default = [])*: Command list (or list of lists, in which case each list of commands will be executed in paralell) to build.
        - a string
        - an array of strings
- **pre_test_commands** *(array\<string\>, default = [])*: Command list to run before running tests.
- **post_test_commands** *(array\<string\>, default = [])*: Command list to run after running tests.
- **services** *(array\<object\>, default = [])*: Service list.
    - **service_name** *(string, default = '')*: The name of the application part.
    - **needed_services** *(array\<string\>, default = [])*: List here the sub apps (as defined by service_name) of our application that are needed for this sub app to run.
    - **sources** *(array\<object\>)*: If specified, this service will be considered as updated only when the content of those directories or files have changed.
        - a file path
        - a directory
    - **config** *(object, optional)*: Deployment configuration. It must be an object with the following fields:
        - **docker_image** *(object, optional)*: Docker to build for running and deploying. It must be an object with the following fields:
            - **name** *(string)*: Name of the docker image to build. By default it will be {:app_name}-{:service_name}. If there is no docker user, it won be pushed to the registry. You can use environment variables.
            - **check_private** *(boolean, default = true
...)*: Check that the docker repository is private before pushing the image.
            - **tag** *(string)*: Tag of the docker image to build. By default it will be {:branch_name}-{:build_id}.
            - **workdir** *(directory path)*: Working directory of the produced docker file, must be an existing directory. By default it will be directory of the dmake file.
            - **copy_directories** *(array\<directory path\>, default = [])*: Directories to copy in the docker image.
            - **install_script** *(file path)*: The install script (will be run in the docker). It has to be executable.
            - **entrypoint** *(file path)*: Set the entrypoint of the docker image generated to run the app.
            - **start_script** *(file path)*: The start script (will be run in the docker). It has to be executable.
        - **docker_opts** *(string, default = '')*: Docker options to add.
        - **ports** *(array\<object\>, default = [])*: Ports to open.
            - **container_port** *(int)*: Port on the container.
            - **host_port** *(int)*: Port on the host.
        - **volumes** *(array\<object\>, default = [])*: Volumes to open.
            - **container_volume** *(string)*: Volume on the container.
            - **host_volume** *(string)*: Volume on the host.
        - **pre_deploy_script** *(string, default = '')*: Scripts to run before launching new version.
        - **mid_deploy_script** *(string, default = '')*: Scripts to run after launching new version and before stopping the old one.
        - **post_deploy_script** *(string, default = '')*: Scripts to run after stopping old version.
    - **tests** *(object, optional)*: Unit tests list. It must be an object with the following fields:
        - **docker_links_names** *(array\<string\>, default = [])*: The docker links names to bind to for this test. Must be declared at the root level of some dmake file of the app.
        - **commands** *(array\<string\>)*: The commands to run for integration tests.
        - **junit_report** *(string)*: Uses JUnit plugin to generate unit test report.
        - **cobertura_report** *(string)*: Publish a Cobertura report (not working for now).
        - **html_report** *(object, optional)*: Publish an HTML report. It must be an object with the following fields:
            - **directory** *(string)*: Directory of the html pages.
            - **index** *(string, default = index.html
...)*: Main page.
            - **title** *(string, default = HTML Report
...)*: Main page title.
    - **deploy** *(object, optional)*: Deploy stage. It must be an object with the following fields:
        - **deploy_name** *(string)*: The name used for deployment. Will default to "${DMAKE_DEPLOY_PREFIX}-app_name-service_name" if not specified.
        - **stages** *(array\<object\>)*: Deployment possibilities.
            - **description** *(string)*: Deploy stage description.
            - **branches** *(mixed, default = [stag])*: Branch list for which this stag is active, '*' can be used to match any branch. Can also be a simple string. It can be one of the followings:
                - a string
                - an array of strings
            - **env** *(free style object, default = {})*: Additionnal environment variables for deployment.
            - **aws_beanstalk** *(object, optional)*: Deploy via Elastic Beanstalk. It must be an object with the following fields:
                - **region** *(string, default = eu-west-1
...)*: The AWS region where to deploy.
                - **stack** *(string, default = 64bit Amazon Linux 2016.03 v2.1.6 running Docker 1.11.2
...)*:
                - **options** *(file path)*: AWS Option file as described here: http://docs.aws.amazon.com/elasticbeanstalk/latest/dg/command-options-general.html.
                - **credentials** *(string, default = S3 path to the credential file to aurthenticate a private docker repository.
...)*:
            - **ssh** *(object, optional)*: Deploy via SSH. It must be an object with the following fields:
                - **user** *(string)*: User name.
                - **host** *(string)*: Host address.
                - **port** *(int, default = '22')*: SSH port.

## Example

You will find below an example of dmake.yml file:

```yaml
dmake_version: '0.1'
app_name: my_app
blacklist:
- some/sub/dmake.yml
env:
    default:
        source: Some string
        variables:
            ENV_TYPE: dev
    branches:
        master:
            ENV_TYPE: prod
docker: some/path/example
docker_links:
-   image_name: mongo:3.2
    link_name: mongo
    deployed_options: -v /mnt:/data
    testing_options: -v /mnt:/data
build:
    env:
        testing:
            ENV_TYPE: dev
            MY_ENV_VARIABLE: '1'
        production:
            ENV_TYPE: dev
            MY_ENV_VARIABLE: '1'
    commands:
    - cmake .
    - make
pre_test_commands:
- Some string
post_test_commands:
- Some string
services:
-   service_name: api
    needed_services:
    - worker
    sources: path/to/app
    config:
        docker_image:
            name: Some string
            check_private: true
            tag: Some string
            workdir: some/directory/example
            copy_directories:
            - some/directory/example
            install_script: install.sh
            entrypoint: some/relative/path/example
            start_script: start.sh
        docker_links_names:
        - mongo
        docker_opts: --privileged
        ports:
        -   container_port: 8000
            host_port: 80
        volumes:
        -   container_volume: /mnt
            host_volume: /mnt
        pre_deploy_script: my/pre_deploy/script
        mid_deploy_script: my/mid_deploy/script
        post_deploy_script: my/post_deploy/script
    tests:
        docker_links_names:
        - mongo
        commands:
        - python manage.py test
        junit_report: test-reports/*.xml
        html_report:
            directory: reports
            index: index.html
            title: HTML Report
    deploy:
        stages:
        -   description: Deployment on AWS and via SSH
            branches:
            - stag
            env:
                AWS_ACCESS_KEY_ID: '1234'
                AWS_SECRET_ACCESS_KEY: abcd
            aws_beanstalk:
                region: eu-west-1
                stack: 64bit Amazon Linux 2016.03 v2.1.6 running Docker 1.11.2
                options: path/to/options.txt
                credentials: S3 path to the credential file to aurthenticate a private
                    docker repository.
            ssh:
                user: ubuntu
                host: 192.168.0.1
                port: '22'

```
