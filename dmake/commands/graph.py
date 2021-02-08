import dmake.common as common
import dmake.core as core


def entry_point(options):
    loaded_files = core.make(options, parse_files_only=True)

    from graphviz import Digraph

    def sanitize_id(name):
        # there is a bug in graphviz around `:` escaping, see https://github.com/xflr6/graphviz/issues/53
        return str(name).replace(':', '_')

    def label(name, file):
        return "<{}<br/><i><font point-size='10'>{}</font></i>>".format(name, file)

    dot = Digraph(comment='DMake Services', filename=options.output, format=options.format)
    dot.attr('node', shape='box', style='filled', fillcolor='grey95')
    dot.attr('edge', color='grey50')
    services_graph = Digraph()
    links_graph = Digraph()
    links_graph.attr(rank='same')

    for file, dmake_file in loaded_files.items():
        app_name = dmake_file.get_app_name()

        for service in dmake_file.get_services():
            service_full_name = "%s/%s" % (app_name, service.service_name)

            service_node_id = sanitize_id(service_full_name)
            services_graph.node(service_node_id,
                                label=label(service_full_name, file))

            for dep in service.needed_services:
                dep_full_name = "%s/%s" % (app_name, dep.service_name)
                dot.edge(service_node_id, sanitize_id(dep_full_name))

            for link_name in service.needed_links:
                link_full_name = "link/%s/%s" % (app_name, link_name)
                dot.edge(service_node_id, sanitize_id(link_full_name), style='dashed')

        for link in dmake_file.docker_links:
            link_full_name = "link/%s/%s" % (app_name, link.link_name)
            link_name = "%s/%s" % (app_name, link.link_name)
            links_graph.node(sanitize_id(link_full_name),
                             label=label(link_name, file),
                             style='dashed,filled', color='grey50', fillcolor='grey98')

    dot.subgraph(services_graph)
    dot.subgraph(links_graph)

    dot.render()
    common.logger.info("Generated graph in files '{}' and '{}'. You can open the first with `xdot` for example.".format(options.output, options.output + '.' + options.format))
