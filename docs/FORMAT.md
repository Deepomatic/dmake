- **dmake_version** *(mixed)*: The dmake version. It can be one of the followings:
    - a number
    - a string
- **app_name** *(string)*: The application name.
- **blocklist** *(array\<file path\>, default = `[]`)*: List of dmake files to ignore.
- **blacklist** *(array\<file path\>, default = `[]`)*: Deprecated. Prefer use of 'blocklist'.
- **env** *(mixed)*: Environment variables to embed in built docker images. It can be one of the followings:
    - a file path
    - an object with the following fields:
        - **default** *(object, optional)*: List of environment variables that will be set by default. It must be an object with the following fields:
            - **source** *(string)*: Source a bash file which defines the environment variables before evaluating the strings of environment variables passed in the *variables* field. It might contain environment variables itself.
            - **variables** *(free style object, default = `{}`)*: Defines environment variables used for the services declared in this file. You might use pre-defined environment variables (or variables sourced from the file defined in the *source* field).
        - **branches** *(free style object, default = `{}`)*: If the branch matches one of the following fields, those variables will be defined as well, eventually replacing the default.
            - **source** *(string)*: Source a bash file which defines the environment variables before evaluating the strings of environment variables passed in the *variables* field. It might contain environment variables itself.
            - **variables** *(free style object, default = `{}`)*: Defines environment variables used for the services declared in this file. You might use pre-defined environment variables (or variables sourced from the file defined in the *source* field).
- **volumes** *(array\<object\>, default = `[]`)*: List of shared volumes usabled on services and docker_links.
    - **name** *(string)*: Shared volume name.
- **docker** *(mixed)*: The environment in which to build and deploy. It can be one of the followings:
    - a file path to another dmake file (which will be added to dependencies) that declares a docker field, in which case it replaces this file's docker field.
    - an object with the following fields:
        - **root_image** *(mixed)*: The default source image name to build on. It can be one of the followings:
            - a file path to another dmake file, in which base the root_image will be this file's base_image.
            - an object with the following fields:
                - **name** *(string)*: Root image name.
                - **tag** *(string)*: Root image tag (you can use environment variables).
        - **base_image** *(mixed, default = `[]`)*: Base (development environment) imags. It can be one of the followings:
            - an object with the following fields:
                - **name** *(string)*: Base image name. If no docker user (namespace) is indicated, the image will be kept locally, otherwise it will be pushed.
                - **variant** *(string)*: When multiple base_image are defined, this names the base_image variant.
                - **root_image** *(string)*: The source image to build on. Defaults to docker.root_image.
                - **raw_root_image** *(boolean, default = `False`)*: If true, don't install anything on the root_image before executing install_scripts.
                - **version** *(string, default = `latest`)*: Deprecated, not used anymore, will be removed later.
                - **install_scripts** *(array\<file path\>, default = `[]`)*: 
                - **python_requirements** *(file path, default = ``)*: Path to python requirements.txt.
                - **python3_requirements** *(file path, default = ``)*: Path to python requirements.txt.
                - **copy_files** *(array\<file or directory path\>, default = `[]`)*: Files to copy. Will be copied before scripts are ran. Paths need to be sub-paths to the build file to preserve MD5 sum-checking (which is used to decide if we need to re-build docker base image). A file 'foo/bar' will be copied in '/base/user/foo/bar'.
                - **mount_secrets** *(free style object, default = `{}`)*: Secrets files to mount on '/run/secrets/<secret_id>' during base image build (uses docker buildkit https://github.com/moby/buildkit/blob/master/frontend/dockerfile/docs/syntax.md#run---mounttypesecret). Double quotes are not supported in the path.
            - an array of objects with the following fields:
                - **name** *(string)*: Base image name. If no docker user (namespace) is indicated, the image will be kept locally, otherwise it will be pushed.
                - **variant** *(string)*: When multiple base_image are defined, this names the base_image variant.
                - **root_image** *(string)*: The source image to build on. Defaults to docker.root_image.
                - **raw_root_image** *(boolean, default = `False`)*: If true, don't install anything on the root_image before executing install_scripts.
                - **version** *(string, default = `latest`)*: Deprecated, not used anymore, will be removed later.
                - **install_scripts** *(array\<file path\>, default = `[]`)*: 
                - **python_requirements** *(file path, default = ``)*: Path to python requirements.txt.
                - **python3_requirements** *(file path, default = ``)*: Path to python requirements.txt.
                - **copy_files** *(array\<file or directory path\>, default = `[]`)*: Files to copy. Will be copied before scripts are ran. Paths need to be sub-paths to the build file to preserve MD5 sum-checking (which is used to decide if we need to re-build docker base image). A file 'foo/bar' will be copied in '/base/user/foo/bar'.
                - **mount_secrets** *(free style object, default = `{}`)*: Secrets files to mount on '/run/secrets/<secret_id>' during base image build (uses docker buildkit https://github.com/moby/buildkit/blob/master/frontend/dockerfile/docs/syntax.md#run---mounttypesecret). Double quotes are not supported in the path.
        - **mount_point** *(string, default = `/app`)*: Mount point of the app in the built docker image. Needs to be an absolute path.
        - **command** *(string, default = `bash`)*: Only used when running 'dmake shell': command passed to `docker run`.
- **docker_links** *(array\<object\>, default = `[]`)*: List of link to create, they are shared across the whole application, so potentially across multiple dmake files.
    - **image_name** *(string)*: Name and tag of the image to launch.
    - **link_name** *(string)*: Link name.
    - **volumes** *(array\<object\>, default = `[]`)*: Either shared volumes to mount. Or: for the 'shell' command only. The list of volumes to mount on the link. It must be in the form ./host/path:/absolute/container/path. Host path is relative to the dmake file.
        - an object with the following fields:
            - **source** *(string)*: The shared volume name (declared in root `volumes`).
            - **target** *(string)*: The path in the container where the volume is mounted.
        - an object with the following fields:
            - **container_volume** *(string)*: Path of the volume mounted in the container.
            - **host_volume** *(string)*: Path of the volume from the host.
    - **need_gpu** *(boolean, default = `False`)*: Whether the docker link needs to be run on a GPU node.
    - **testing_options** *(string, default = ``)*: Additional Docker options when testing on Jenkins.
    - **probe_ports** *(mixed, default = `auto`)*: Either 'none', 'auto' or a list of ports in the form 1234/tcp or 1234/udp. It can be one of the followings:
        - a string
        - an array of strings
    - **env** *(free style object, default = `{}`)*: Additional environment variables defined when running this image.
    - **env_exports** *(free style object, default = `{}`)*: A set of environment variables that will be exported in services that use this link when testing.
- **build** *(object)*: Commands to run for building the application. It must be an object with the following fields:
    - **env** *(free style object, default = `{}`)*: List of environment variables used when building applications (excluding base_image).
    - **commands** *(array\<object\>, default = `[]`)*: Command list (or list of lists, in which case each list of commands will be executed in paralell) to build.
        - a string
        - an array of strings
- **pre_test_commands** *(array\<string\>, default = `[]`)*: Deprecated, not used anymore, will be removed later. Use `tests.commands` instead.
- **post_test_commands** *(array\<string\>, default = `[]`)*: Deprecated, not used anymore, will be removed later. Use `tests.commands` instead.
- **services** *(array\<object\>, default = `[]`)*: Service list.
    - **service_name** *(string, default = ``)*: The name of the application part.
    - **needed_services** *(array\<object\>, default = `[]`)*: List here the sub apps (as defined by service_name) of our application that are needed for this sub app to run.
        - **service_name** *(string)*: The name of the needed application part.
        - **link_name** *(string)*: Link name.
        - **env** *(free style object, default = `{}`)*: List of environment variables that will be set when executing the needed service.
        - **env_exports** *(free style object, default = `{}`)*: A set of environment variables that will be exported in services that use this service when testing.
        - **needed_for** *(object)*: When is this dependency service needed for?. It must be an object with the following fields:
            - **run** *(boolean, default = `True`)*: Parent service `run` needs this dependency service.
            - **test** *(boolean, default = `True`)*: Parent service `test` needs this dependency service.
            - **trigger_test** *(boolean, default = `True`)*: Parent service `test` is triggered by this dependency service change.
        - **use_host_ports** *(boolean)*: Set to false to disable exposing internal dependency service ports on host, without impacting his feature when that service is directly started.
    - **needed_links** *(array\<string\>, default = `[]`)*: The docker links names to bind to for this test. Must be declared at the root level of some dmake file of the app.
    - **sources** *(array\<object\>)*: If specified, this service will be considered as updated only when the content of those directories or files have changed.
        - a file path
        - a directory
    - **dev** *(object)*: Development runtime configuration. It must be an object with the following fields:
        - **entrypoint** *(file path)*: Set the entrypoint used with `dmake shell`.
    - **config** *(object)*: Deployment configuration. It must be an object with the following fields:
        - **docker_image** *(mixed)*: Docker image to use for running and deploying. It can be one of the followings:
            - a string
            - an object with the following fields:
                - **name** *(string)*: Name of the docker image to build. By default it will be {:app_name}-{:service_name}. If there is no docker user, it won be pushed to the registry. You can use environment variables.
                - **base_image_variant** *(mixed)*: Specify which `base_image` variants are used as `base_image` for this service. Array: multi-variant service. Default: first 'docker.base_image'. It can be one of the followings:
                    - a string
                    - an array of strings
                - **source_directories_additional_contexts** *(array\<string\>, default = `[]`)*: NOT RECOMMENDED. Additional source directories contexts for changed services auto detection in case of build context going outside of the dmake.yml directory.
                - **check_private** *(boolean, default = `True`)*: Check that the docker repository is private before pushing the image.
                - **tag** *(string, default = `${_BRANCH_SANITIZED_FOR_DOCKER}-${_BUILD_ID_OR_LATEST}${_VARIANT_SUFFIX}`)*: Tag of the docker image to build (with extra environment variables available only for this field: prefixed by '_').
                - **aliases** *(array\<string\>, default = `[]`)*: Add image name aliases, useful when wanting to push to multiple registries.
                - **workdir** *(directory path)*: Working directory of the produced docker file, must be an existing directory. By default it will be directory of the dmake file.
                - **copy_directories** *(array\<directory path\>, default = `[]`)*: Directories to copy in the docker image.
                - **install_script** *(file path)*: The install script (will be run in the docker). It has to be executable.
                - **entrypoint** *(file path)*: Set the entrypoint of the docker image generated to run the app.
                - **start_script** *(file path)*: The start script (will be run in the docker). It has to be executable.
            - an object with the following fields:
                - **name** *(string)*: Name of the docker image to build. By default it will be {:app_name}-{:service_name}. If there is no docker user, it won be pushed to the registry. You can use environment variables.
                - **base_image_variant** *(mixed)*: Specify which `base_image` variants are used as `base_image` for this service. Array: multi-variant service. Default: first 'docker.base_image'. It can be one of the followings:
                    - a string
                    - an array of strings
                - **source_directories_additional_contexts** *(array\<string\>, default = `[]`)*: NOT RECOMMENDED. Additional source directories contexts for changed services auto detection in case of build context going outside of the dmake.yml directory.
                - **check_private** *(boolean, default = `True`)*: Check that the docker repository is private before pushing the image.
                - **tag** *(string, default = `${_BRANCH_SANITIZED_FOR_DOCKER}-${_BUILD_ID_OR_LATEST}${_VARIANT_SUFFIX}`)*: Tag of the docker image to build (with extra environment variables available only for this field: prefixed by '_').
                - **aliases** *(array\<string\>, default = `[]`)*: Add image name aliases, useful when wanting to push to multiple registries.
                - **build** *(object)*: Docker build options for service built using user-provided Dockerfile (ignore `.build.commands`), like in Docker Compose files.`. It must be an object with the following fields:
                    - **context** *(directory path)*: Docker build context directory.
                    - **dockerfile** *(string)*: Alternate Dockerfile, relative path to `context` directory.
                    - **args** *(free style object, default = `{}`)*: Add build arguments, which are environment variables accessible only during the build process. Higher precedence than `.build.env`.
                    - **labels** *(free style object, default = `{}`)*: Add metadata to the resulting image using Docker labels. It's recommended that you use reverse-DNS notation to prevent your labels from conflicting with those used by other software.
                    - **target** *(string)*: Build the specified stage as defined inside the Dockerfile. See the [multi-stage build docs](https://docs.docker.com/engine/userguide/eng-image/multistage-build/) for details.
        - **docker_opts** *(string, default = ``)*: Docker options to add.
        - **env_override** *(free style object, default = `{}`)*: Extra environment variables for this service. Overrides dmake.yml root `env`, with variable substitution evaluated from it.
        - **need_gpu** *(boolean, default = `False`)*: Whether the service needs to be run on a GPU node.
        - **ports** *(array\<object\>, default = `[]`)*: Ports to open.
            - **container_port** *(int)*: Port on the container.
            - **host_port** *(int)*: Port on the host. If not set, a random port will be used.
        - **volumes** *(array\<object\>, default = `[]`)*: Volumes to mount.
            - an object with the following fields:
                - **source** *(string)*: The shared volume name (declared in root `volumes`).
                - **target** *(string)*: The path in the container where the volume is mounted.
            - an object with the following fields:
                - **container_volume** *(string)*: Path of the volume mounted in the container.
                - **host_volume** *(string)*: Path of the volume from the host.
        - **readiness_probe** *(object, optional)*: A probe that waits until the container is ready. It must be an object with the following fields:
            - **command** *(array\<string\>, default = `[]`)*: The command to run to check if the container is ready. The command should fail with a non-zero code if not ready.
            - **initial_delay_seconds** *(int, default = `0`)*: The delay before the first probe is launched.
            - **period_seconds** *(int, default = `5`)*: The delay between two first probes.
            - **max_seconds** *(int, default = `0`)*: The maximum delay after failure.
        - **devices** *(array\<string\>, default = `[]`)*: Device to expose from the host to the container. Support variable substitution in host part, to have a generic dmake.yml with host-specific values configured externally, per machine.
    - **tests** *(object, optional)*: Unit tests configuration. Some parts of the configuration are also used in dmake shell. It must be an object with the following fields:
        - **docker_links_names** *(array\<string\>, default = `[]`)*: The docker links names to bind to for this test. Must be declared at the root level of some dmake file of the app.
        - **data_volumes** *(array\<object\>, default = `[]`)*: The data volumes to mount. Used for test and shell.
            - **container_volume** *(string)*: Path of the volume mounted in the container.
            - **source** *(string)*: Host path and s3 URLs are supported.
            - **read_only** *(boolean, default = `False`)*: Flag to set the volume as read-only.
        - **commands** *(array\<string\>)*: The commands to run for integration tests.
        - **timeout** *(mixed)*: The timeout (in seconds) to apply to the tests execution (excluding dependencies, setup, and potential resources locks). It can be one of the followings:
            - a number
            - a string
        - **junit_report** *(mixed, default = `[]`)*: Filepath or array of file paths of xml xunit test reports. Publish a XUnit test report. It can be one of the followings:
            - a string
            - an array of strings
        - **cobertura_report** *(mixed, default = `[]`)*: Filepath or array of file paths of xml xunit test reports. Publish a Cobertura report. It can be one of the followings:
            - a string
            - an array of strings
        - **html_report** *(object, optional)*: Publish an HTML report. It must be an object with the following fields:
            - **directory** *(string)*: Directory of the html pages.
            - **index** *(string, default = `index.html`)*: Main page.
            - **title** *(string, default = `HTML Report`)*: Main page title.
    - **deploy** *(object, optional)*: Deploy stage. It must be an object with the following fields:
        - **deploy_name** *(string)*: The name used for deployment. Will default to '{:app_name}-{:service_name}' if not specified.
        - **stages** *(array\<object\>)*: Deployment possibilities.
            - **description** *(string)*: Deploy stage description.
            - **branches** *(mixed, default = `[stag]`)*: Branch list for which this stag is active, '*' can be used to match any branch. Can also be a simple string. It can be one of the followings:
                - a string
                - an array of strings
            - **env** *(free style object, default = `{}`)*: Additionnal environment variables for deployment.
            - **aws_beanstalk** *(object, optional)*: Deploy via Elastic Beanstalk. It must be an object with the following fields:
                - **name_prefix** *(string, default = `${DMAKE_DEPLOY_PREFIX}`)*: The prefix to add to the 'deploy_name'. Can be useful as application name have to be unique across all users of Elastic BeanStalk.
                - **region** *(string, default = `eu-west-1`)*: The AWS region where to deploy.
                - **stack** *(string, default = `64bit Amazon Linux 2016.03 v2.1.6 running Docker 1.11.2`)*: 
                - **options** *(file path)*: AWS Option file as described here: http://docs.aws.amazon.com/elasticbeanstalk/latest/dg/command-options-general.html.
                - **credentials** *(string)*: S3 path to the credential file to authenticate a private docker repository.
                - **ebextensions** *(directory path)*: Path to the ebextension directory. See http://docs.aws.amazon.com/elasticbeanstalk/latest/dg/ebextensions.html.
            - **ssh** *(object, optional)*: Deploy via SSH. It must be an object with the following fields:
                - **user** *(string)*: User name.
                - **host** *(string)*: Host address.
                - **port** *(int, default = `22`)*: SSH port.
            - **k8s_continuous_deployment** *(object, optional)*: Continuous deployment via Kubernetes. Look for all the deployments running this service. It must be an object with the following fields:
                - **context** *(string)*: kubectl context to use.
                - **namespace** *(string, default = `default`)*: Kubernetes namespace to target.
                - **selectors** *(free style object, default = `{}`)*: Selectors to restrict the deployment.
            - **kubernetes** *(object, optional)*: Deploy to Kubernetes cluster. It must be an object with the following fields:
                - **context** *(string)*: kubectl context to use.
                - **namespace** *(string)*: Kubernetes namespace to target (overrides kubectl context default namespace.
                - **manifest** *(object)*: Kubernetes manifest defining all the resources needed to deploy the service.
                    - **template** *(file path)*: Kubernetes manifest file (Python PEP 292 template format) defining all the resources needed to deploy the service.
                    - **variables** *(free style object, default = `{}`)*: Defines variables used in the kubernetes manifest template.
                - **manifests** *(array\<object\>, default = `[]`)*: Kubernetes manifests defining resources needed to deploy the service.
                    - **template** *(file path)*: Kubernetes manifest file (Python PEP 292 template format) defining all the resources needed to deploy the service.
                    - **variables** *(free style object, default = `{}`)*: Defines variables used in the kubernetes manifest template.
                - **config_maps** *(array\<object\>, default = `[]`)*: Additional Kubernetes ConfigMaps.
                    - **name** *(string)*: Kubernetes ConfigMap name.
                    - **from_files** *(array\<object\>, default = `[]`)*: Kubernetes create values from files.
                        - **key** *(string)*: File key.
                        - **path** *(file path)*: File path (relative to this dmake.yml file).
                - **secrets** *(array\<object\>, default = `[]`)*: Additional Kubernetes Secrets.
                    - **name** *(string)*: Kubernetes Secret name.
                    - **generic** *(object)*: Kubernetes Generic Secret type parameters.
                        - **from_files** *(array\<object\>, default = `[]`)*: Kubernetes create values from files.
                            - **key** *(string)*: File key.
                            - **path** *(string)*: Absolute file path. Supports variables substitution.
