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
