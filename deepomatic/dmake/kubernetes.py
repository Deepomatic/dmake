import hashlib
import json
import yaml

def get_env_hash(env):
    """Return a stable hash for the `env` environment."""
    return hashlib.sha256(json.dumps(sorted(env.items()))).hexdigest()[:10]

def generate_config_map(env, name):
    """Return a kubernetes manifest defining a ConfigMap storing `env`."""
    data = yaml.load("""
apiVersion: v1
kind: ConfigMap
metadata:
  name: ""
data: {}
""")
    data['metadata']['name'] = name
    data['data'] = env
    return data

def generate_config_map_file(env, name_prefix, output_filepath):
    """Generate a ConfigMap manifest file with unique env-hashed name, and return the name."""
    env_hash = get_env_hash(env)
    name = "%s-env-%s" % (name_prefix, env_hash)
    data = generate_config_map(env, name)
    with open(output_filepath, 'w') as configmap_file:
        yaml.dump(data, configmap_file, default_flow_style=False)
    return name
