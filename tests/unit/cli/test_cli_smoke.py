from __future__ import annotations

from country_compare.cli.main import build_parser, main


def test_cli_parser_accepts_supported_commands():
    parser = build_parser()

    assert parser.parse_args(["validate-config"]).command == "validate-config"
    assert parser.parse_args(["validate-data"]).command == "validate-data"
    assert parser.parse_args(["update-data", "--manifest", "config/source.yaml"]).command == "update-data"


def test_demo_command_is_explicit_placeholder(capsys):
    exit_code = main(["demo"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "planned for Phase 8-B" in captured.out