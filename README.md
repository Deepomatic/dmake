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
- Docker 1.13 or newer

**DMake** uses an experimental feature of docker to squash images during build; you need to enable experimental features on your docker configuration:
- Add to `/etc/docker/daemon.json`
```
{
  "experimental": true
}
```
- Restart docker daemon:
```
sudo systemctl restart docker.service
```

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

See auto-generated [format documentation](docs/FORMAT.md) and [`dmake.yml` example](docs/EXAMPLE.md).
