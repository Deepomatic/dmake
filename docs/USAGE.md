```
usage: dmake [-h] [--debug-graph] [--debug-graph-and-exit]
             [--debug-graph-group-by {command,height}] [--debug-graph-pretty]
             [--debug-graph-output-filename DEBUG_GRAPH_OUTPUT_FILENAME]
             [--debug-graph-output-format DEBUG_GRAPH_OUTPUT_FORMAT]
             {test,build,run,stop,shell,deploy,release,graph,generate-doc,completion}
             ...

optional arguments:
  -h, --help            show this help message and exit
  --debug-graph         Generate dmake steps DOT graph for debug purposes.
  --debug-graph-and-exit
                        Generate dmake steps DOT graph for debug purposes then
                        exit.
  --debug-graph-group-by {command,height}
                        Group nodes by <> in generated DOT graph.
  --debug-graph-pretty, --no-debug-graph-pretty
                        Pretty or raw output for debug graph.
  --debug-graph-output-filename DEBUG_GRAPH_OUTPUT_FILENAME
                        The generated DOT graph filename. Defaults to 'dmake-
                        services.debug.{group_by}.gv'
  --debug-graph-output-format DEBUG_GRAPH_OUTPUT_FORMAT
                        The generated DOT graph format (`png`, `svg`, `pdf`,
                        ...).

Commands:
  {test,build,run,stop,shell,deploy,release,graph,generate-doc,completion}
    test                Launch tests for the whole repo or, if specified, an
                        app or one of its services.
    build               Launch the build for the whole repo or, if specified,
                        an app or one of its services.
    run                 Launch the application or only one of its services.
    stop                Stop the containers started by dmake for the current
                        repository and branch. Usually by 'dmake run', but can
                        also be useful to cleanup aborted executions of dmake.
    shell               Run a shell session withing a docker container with
                        the environment set up for a given service.
    deploy              Deploy specified apps and services.
    release             Create a Github release (with changelog) of the app
                        based on a previously created git tag.
    graph               Generate a visual graph of the app services
                        dependencies (dot/graphviz format).
    generate-doc        Generate DMake documentation.
    completion          Output shell completion code for bash (may work for
                        zsh)
```
