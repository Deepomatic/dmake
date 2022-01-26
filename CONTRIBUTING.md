Kubernetes tests: they consist in just generating the kubernetes yamls, and validate them against a cluster and namespace (with `kubectl apply --dry-run=server`), all at the dmake plan phase.
- first, set `DMAKE_TEST_K8S_CONTEXT` and `DMAKE_TEST_K8S_NAMESPACE` environment variables to a working cluster, having 2 namespaces already created: `${DMAKE_TEST_K8S_NAMESPACE}` and `${DMAKE_TEST_K8S_NAMESPACE}-2`
- finally, run the plan-only part of the deployment of [`./test/k8s/`](./test/k8s/dmake.yml)): `DMAKE_ON_BUILD_SERVER=1 dmake deploy test-k8s --branch=master`

more details:
- you can debug thins with `DMAKE_LOGLEVEL=DEBUG` and look for `kubectl` calls
- see [`Jenkinsfile`](./Jenkinsfile#L119-L126) for how it's configured on Jenkins
