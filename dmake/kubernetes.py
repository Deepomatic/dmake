import hashlib
import json
import yaml

import dmake.common as common


def get_env_hash(env):
    """Return a stable hash for the `env` environment."""
    serialized_env = json.dumps(sorted(env.items()))
    serialized_env_binary = str(serialized_env).encode('UTF-8')
    return hashlib.sha256(serialized_env_binary).hexdigest()[:10]


def generate_config_map(env, name, labels = None, annotations = None):
    """Return a kubernetes manifest defining a ConfigMap storing `env`."""
    data = yaml.safe_load("""
apiVersion: v1
kind: ConfigMap
metadata:
  name: ""
  labels: {}
  annotations: {}
data: {}
""")
    data['metadata']['name'] = name
    if labels:
        data['metadata']['labels'] = labels
    if annotations:
        data['metadata']['annotations'] = annotations
    data['data'] = env
    return data


def generate_config_map_file(env, name_prefix, output_filepath, labels = None, annotations = None):
    """Generate a ConfigMap manifest file with unique env-hashed name, and return the name."""
    env_hash = get_env_hash(env)
    name = "%s-env-%s" % (name_prefix, env_hash)
    data = generate_config_map(env, name, labels, annotations)
    with open(output_filepath, 'w') as configmap_file:
        yaml.dump(data, configmap_file, default_flow_style=False)
    return name


def add_metadata(resource, labels = None, annotations = None):
    if labels:
        if 'labels' not in resource['metadata']:
            resource['metadata']['labels'] = {}
        resource['metadata']['labels'].update(labels)
    if annotations:
        if 'annotations' not in resource['metadata']:
            resource['metadata']['annotations'] = {}
        resource['metadata']['annotations'].update(annotations)


def dump_all_str_and_add_metadata(data_str_or_list_of_str, labels=None, annotations=None, file=None):
    """
    Input:
    - either a str for one or more yamls;
    - or a list of str for one yaml
    Output:
    multi element yaml str (or written to file if specified), with labels and annotations injected in metadata (and annotations also added to spec.template.metadata when it exists).
    """
    if isinstance(data_str_or_list_of_str, list):
        data = [common.yaml_ordered_load(data_str) for data_str in data_str_or_list_of_str]
    else:
        data = common.yaml_ordered_load(data_str_or_list_of_str, all=True)
    for resource in data:
        # add to metadata
        add_metadata(resource, labels, annotations)
        # add to spec.template.metadata if spec.template exists, e.g. to pods templates
        if 'spec' in resource and 'template' in resource['spec']:
            add_metadata(resource['spec']['template'], annotations=annotations)
    return common.yaml_ordered_dump(data, file, all=True)


def generate_from_create(args, name, from_file_args):
    program = 'kubectl'
    args = ['create'] + args + ['--dry-run=true', '--output=yaml', name] + from_file_args
    cmd = '%s %s' % (program, ' '.join(map(common.wrap_cmd, args)))
    manifest = common.run_shell_command(cmd, raise_on_return_code=True)
    return manifest
