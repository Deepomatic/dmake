# DMake v0.1

**DMake** is a tool to manage micro-service based applications. It allows to easily build, run, test and deploy an entire application or one of its micro-services.

Table of content:
- [Installation](#installation)
- [Tutorial](#tutorial)
- [Using DMake with Jenkins](#using-dmake-with-jenkins)
- [Configuring Docker](#configuring-docker)
- [Documentation](#documentation)

## Installation

In order to run **DMake**, you will need:
- Python 2.7 or 3.5+
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

After following the instructions, check that **DMake** is found by running:

```
$ dmake help
```

It should display the help message with the list of commands.

## Tutorial

To start the tutorial, enter the tutorial directory:

```
$ cd tutorial
```

For those who just want to see the results, just run:

```
$ dmake run -d web
```

Once it has completed, the factorial demo is available at [http://localhost:8000](http://localhost:8000)

Before moving to the details, do not forget to shutdown the launched containers with:

```
$ dmake stop
```

Alright ! To simulate an application made of several micro-services, this project is made of two services:
- a Django app that shows a form where you enter a number '*n*', in the `web/` directory.
- a worker that computes factorial '*n*', in the `worker/` directory.
- an end-to-end test testing the `web` service, in the `e2e/` directory.

**DMake** allows you to specify how your whole app should be tested and run by relying on `dmake.yml` files. **DMake** searches for the whole repository and parses all those files. In this project, there are 3: one in each of the sub-directories.

Let's start with the **DMake** configuration of the worker that computes the factorial by having a look at [worker/dmake.yml](worker/dmake.yml).

### [worker/dmake.yml](worker/dmake.yml)

#### header
The two first lines indicate the version of **DMake** that will parse the YAML file and the name of your app:

```yaml
dmake_version: 0.1
app_name: dmake-tutorial
```

The `app_name` is used to group the multiple services of an app together, allowing **DMake** to separately process several apps in the same repository.

#### `env`
We then declare the runtime environment variables:
```yaml
env:
  default:
    variables:
      AMQP_URL: amqp://rabbitmq/dev
```
They will be injected into the containers at runtime, but can also be used in many `dmake.yml` values with bash syntaxe (e.g. `key: ${FOO}-bar`).

You define default environment variables (common plus usually values for development purposes) in `default`, and may also specify variables specific to a branch (in `branches`) (used when deploying our app), in which case the default value of the variable is overridden.


#### `docker`
Then comes the specification of the Docker environment in which your app will run: the base image
```yaml
docker:
  base_image:
    name: dmake-tutorial-worker-base
    root_image: ubuntu:16.04
    install_scripts:
      - deploy/dependencies.sh
```

The base image is a docker image that contains everything to build and run your service, except for the service code itself: it's the build and runtime dependencies.

Here we declare that our base image starts from Ubuntu 16.04 (the `root_image`), we name it `dmake-tutorial-worker-base`, and list the scripts that will build the base image starting from the root image: `deploy/dependencies.sh`.

This base image is cached so you don't have to rebuild it every time. Furthermore, it is globally cached: it can be pushed to the docker registry and all dmake users will try to pull it before building it. (This works by naming the base image tag with source-based hashes: we hash the root image and base image `install_scripts`: same sources will give same tag).

#### `docker_links`
The next thing to declare are the "external" services that you will need: They are services needed by our app, but not built here. They are shared across the whole application (so no need to re-declare them in another `dmake.yml` file with the same `app_name`):

```yaml
docker_links:
  - image_name: rabbitmq:3.6
    link_name: rabbitmq
    probe_ports:
      - 5672/tcp
    env:
      RABBITMQ_DEFAULT_VHOST: dev
      RABBITMQ_DEFAULT_USER: user
      RABBITMQ_DEFAULT_PASS: password
```

This declares that we will use RabbitMQ 3.6 (Docker image `rabbitmq:3.6`) and that we will refer to it as the `rabbitmq` service. This service will be made available to your app by linking it to its Docker container. We customize the execution of this service with `probe_ports` (to wait for the service to be ready), and `env` to control RabbitMQ execution.

#### `services`
Now that the common parts have been defined, we can declare the services:
Each service is a container with a name, a way to build it, its runtime service dependencies (other dmake or "external" services), how to test it, how to access it, etc.

```yaml
services:
  - service_name: worker
    needed_links:
      - rabbitmq
    config:
      docker_image:
        build:
          context: .
          dockerfile: deploy/Dockerfile
    tests:
      commands:
        - ./bin/worker_test
```

Our `worker` service needs `rabbitmq`, and its `config.docker_image` declares how to build its image: it's the same sub-tree as for docker-compose (the `Dockerfile` allows you to use multi-stage builds for optimal image size and docker build cache re-use).
Finally we declare how to test this service: the command `./bin/worker_test` will be executed in the built service docker image.

#### `build`
Old services can be defined without a `Dockerfile`: a root `build` configuration is used instead: DMake will generate a `Dockerfile` for us. See [web/dmake.yml](web/dmake.yml) (where there is zero build command...).

#### others
There are much more features in DMake (deployment on kubernetes, multiple variants of the base image, etc.. See the full [Documentation](#documentation).


### `dmake` command-line interface

#### `dmake test`
Now that we went through the configuration file, you can try to test the worker with:

```
$ dmake test -d worker
```

The `-d` option tells **DMake** to run all the dependencies of the service as well.

### `dmake shell`
To interactively work on a service, dmake provides a shell access in the service container (running the base image), with the sources mounted into it:

```
$ dmake shell -d worker
```
There you can build an execute your service, and quickly iterate by editting the code from your favorite editor.

### `dmake run`
You can now run the full app with:

```
$ dmake run -d web
```
It will start the `web` service with all its dependencies (RabbitMQ and the worker).

Once it has completed, the factorial demo is available at [http://localhost:8000](http://localhost:8000)

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

It will build a Docker image for Jenkins (cf `jenkins/docker/Dockerfile`) and launch it locally. Once launched, you can access it on [http://localhost:8080/](http://localhost:8080/) and connect with user `admin` and password `password`. You will see a job called `dmake-tutorial`. You can trigger a build of this job by clicking on the "play" button on the right and look at the build's output on [http://localhost:8080/job/dmake-tutorial/job/master/lastBuild/console](http://localhost:8080/job/dmake-tutorial/job/master/lastBuild/console).

In order to setup DMake in your own Jenkins server, you can adjust the Dockerfile in `jenkins/docker/Dockerfile` to your taste.

## Configuring Docker

When experiencing with DMake (either on your own machine or on Jenkins), you may notice that files produced when building your app belong to the root user.

You may check if this is the case on your machine by running `docker run -v `pwd`:/mnt -ti ubuntu touch /mnt/foobar && ls -l foobar && rm foobar`. If the resulting owner of the file is root, you might need to adapt the configuration of Docker as indicated below.

One simple solution would be to perform a `sudo chown $(id -u):$(id -g) -R .` after each build. This is however not very convenient nor suitable.

Another solution consists of configuring Docker to map your user on the host machine to the root user of containers. In the following we assume the default non root user of the machine is `deepomatic` with UID 1000 and GID 1000. You simply need to:
- ensure that the file `/etc/subuid` (respectively `/etc/subgid`) contains a line like `deepomatic:1000:65536` where 1000 stands for your UID (respectively GID).
- Edit the file `/etc/default/docker` so that it contains the following line:
```bash
DOCKER_OPTS="-g /mnt/docker --userns-remap=ubuntu"
```
- Restart Docker: `sudo restart docker`
- If you use the provided Jenkins image, change the Docker socket ownership to your user: e.g. `sudo chown deepomatic /var/run/docker.sock`. This will allow Jenkins to interact with Docker within its container. You need to do this each time you start Jenkins so you might want to include this into Jenkins start script.

This poses another problem when you try to use the Dockerfile provided in this repository for Jenkins: `jenkins/docker/Dockerfile`. As a user called `jenkins` is declared in the original Jenkins Dockerfile, Jenkins won't start because all the file in the container belong to root and not to the `jenkins` user. In order to set the ownership to `jenkins` (with a UID of 1000 and GID 1000) in the container, the files need to have a UID and GID of 2000 on the host machine (or 1000+x if x is the UID/GID of your user). See [Docker Documentation](https://docs.docker.com/engine/reference/commandline/dockerd/#/daemon-user-namespace-options).

A convenient way to achieve this is to create a new `jenkins` user on our machine with the correct UID and GID:

```
$ groupadd -g 2000 jenkins
$ useradd -u 2000 -g 2000 -d ${DMAKE_PATH}/jenkins/jenkins_home -s /bin/bash jenkins
$ chown jenkins:jenkins -R ${DMAKE_PATH}/jenkins/jenkins_home
```

## Documentation

See auto-generated [format documentation](docs/FORMAT.md) and [`dmake.yml` example](docs/EXAMPLE.md).

See also `dmake help` for command-line interface.
