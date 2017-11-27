import yaml
from collections import OrderedDict

from dmake.deepobuild import DMakeFileSerializer

def generate():
    doc_root = DMakeFileSerializer()
    _, _, doc = doc_root.generate_doc()
    print(doc)

def example():
    doc_root = DMakeFileSerializer()
    example = doc_root.generate_example()
    print("```yaml")
    print(yaml.dump(example, default_flow_style = False, indent = 4))
    print("```")

# Needed to output the YAML dictionnary without sorting the fields of the document
def represent_ordereddict(dumper, data):
    value = []
    for item_key, item_value in data.items():
        node_key = dumper.represent_data(item_key)
        node_value = dumper.represent_data(item_value)
        value.append((node_key, node_value))
    return yaml.nodes.MappingNode(u'tag:yaml.org,2002:map', value)
yaml.add_representer(OrderedDict, represent_ordereddict)
