```yaml
dmake_version: '0.1'
app_name: my_app
blocklist:
  - some/sub/dmake.yml
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
volumes:
  - datasets
docker: some/file/example
docker_links:
  - image_name: mongo:3.2
    link_name: mongo
    volumes:
      - datasets:/datasets
      - /mnt:/mnt
    need_gpu: true
    testing_options: -v /mnt:/data
    probe_ports: auto
    env:
      REDIS_URL: ${REDIS_URL}
    env_exports:
      any_key: Some string
build:
  env:
    BUILD: ${BUILD}
  commands:
    - cmake .
    - make
pre_test_commands:
  - Some string
post_test_commands:
  - Some string
services:
  - service_name: api
    needed_services:
      - service_name: worker-nn
        link_name: worker-nn
        env:
          CNN_ID: '2'
        env_exports:
          any_key: Some string
        needed_for:
          run: true
          test: true
          trigger_test: true
    needed_links:
      - mongo
    sources: path/to/app
    dev:
      entrypoint: some/relative/file/example
    config:
      docker_image:
        name: Some string
        base_image_variant:
          - Some string
        source_directories_additional_contexts:
          - ../web
        check_private: true
        tag: Some string
        workdir: some/dir/example
        copy_directories:
          - some/dir/example
        install_script: install.sh
        entrypoint: some/relative/file/example
        start_script: start.sh
      docker_opts: --privileged
      env_override:
        INFO: ${BRANCH}-${BUILD}
      need_gpu: true
      ports:
        - container_port: 8000
          host_port: 80
      volumes:
        - datasets:/datasets
      readiness_probe:
        command:
          - cat
          - /tmp/worker_ready
        initial_delay_seconds: 1
        period_seconds: 5
        max_seconds: 40
      devices:
        - /dev/bus/usb/001/002:/dev/bus/usb/001/002
    tests:
      docker_links_names:
        - mongo
      data_volumes:
        - container_volume: /mnt
          source: s3://my-bucket/some/folder
          read_only: true
      commands:
        - python manage.py test
      timeout: '600'
      junit_report: test-reports/nosetests.xml
      cobertura_report: test-reports/coverage.xml
      html_report:
        directory: test-reports/cover
        index: index.html
        title: HTML Report
    deploy:
      stages:
        - description: Deployment on AWS and via SSH
          branches:
            - stag
          env:
            AWS_ACCESS_KEY_ID: '1234'
            AWS_SECRET_ACCESS_KEY: abcd
          aws_beanstalk:
            name_prefix: ${DMAKE_DEPLOY_PREFIX}
            region: eu-west-1
            stack: 64bit Amazon Linux 2016.03 v2.1.6 running Docker 1.11.2
            options: path/to/options.txt
            credentials: Some string
            ebextensions: some/dir/example
          ssh:
            user: ubuntu
            host: 192.168.0.1
            port: 22
          k8s_continuous_deployment:
            context: Some string
            namespace: default
            selectors:
              any_key: Some string
          kubernetes:
            context: Some string
            namespace: Some string
            manifest:
              template: path/to/kubernetes-manifest.yaml
              variables:
                TLS_SECRET_NAME: ${K8S_DEPLOY_TLS_SECRET_NAME}
            manifests:
              - template: path/to/kubernetes-manifest.yaml
                variables:
                  TLS_SECRET_NAME: ${K8S_DEPLOY_TLS_SECRET_NAME}
            config_maps:
              - name: nginx
                from_files:
                  - key: nginx.conf
                    path: deploy/nginx.conf
            secrets:
              - name: ssh-key
                generic:
                  from_files:
                    - key: ssh-privatekey
                      path: ${SECRETS}/ssh_id_rsa

```
