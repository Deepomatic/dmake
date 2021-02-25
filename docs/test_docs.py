import os

import pytest

from dmake import cli, common

doc_kind_list = [
    'usage',
    'format',
    'example',
]
@pytest.mark.parametrize("kind", doc_kind_list)
def test_docs_up_to_date(kind, capsys):
    path = os.path.dirname(__file__)
    expected_doc_path = os.path.join(path, '{KIND}.md'.format(KIND=kind.upper()))
    with open(expected_doc_path, "r") as f:
        expected_doc_source = f.read()

    args = cli.argparser.parse_args(['generate-doc', kind])
    args.func(args)

    captured = capsys.readouterr()
    assert captured.out == expected_doc_source, (
        "Unexpected {KIND}.md documentation file."
        "Rebuild them all with:"
        "\nmake -C {path}".format(KIND=kind.upper(), path=path)
    )
