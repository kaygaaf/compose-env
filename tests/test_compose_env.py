import json
from pathlib import Path

from compose_env.cli import main
from compose_env.refs import iter_references


def _refs(text: str) -> list[tuple[str, bool]]:
    return list(iter_references(text))


def test_reference_forms():
    assert _refs("${TAG}") == [("TAG", False)]
    assert _refs("$TAG") == [("TAG", False)]
    assert _refs("${TAG:-latest}") == [("TAG", True)]
    assert _refs("${TAG-latest}") == [("TAG", True)]
    assert _refs("${TAG:-}") == [("TAG", True)]
    assert _refs("${TAG:?missing}") == [("TAG", False)]
    assert _refs("echo $$HOME") == []
    assert _refs("$${IGNORED} $REAL") == [("REAL", False)]
    assert _refs("price $$ and $KEEP") == [("KEEP", False)]
    assert _refs("${UNSET:-$OTHER}") == [("UNSET", True)]


def test_missing_var(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CE_TEST_TAG", raising=False)
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  web:\n    image: app:${CE_TEST_TAG}\n",
        encoding="utf-8",
    )
    assert main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == "CE_TEST_TAG\n"
    assert captured.err == ""


def test_missing_bare_var(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CE_TEST_BARE", raising=False)
    (tmp_path / "compose.yml").write_text(
        "services:\n  web:\n    image: app:$CE_TEST_BARE\n",
        encoding="utf-8",
    )
    assert main(["-f", "compose.yml"]) == 1
    assert capsys.readouterr().out == "CE_TEST_BARE\n"


def test_set_via_env(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CE_TEST_FROM_ENV", "super-secret-from-env")
    (tmp_path / "compose.yaml").write_text(
        "services:\n  web:\n    image: app:${CE_TEST_FROM_ENV}\n",
        encoding="utf-8",
    )
    assert main([]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "super-secret-from-env" not in captured.out
    assert "super-secret-from-env" not in captured.err


def test_set_via_dotenv(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CE_TEST_FROM_DOTENV", raising=False)
    (tmp_path / ".env").write_text(
        "# comment\nexport CE_TEST_FROM_DOTENV=super-secret-from-dotenv\n\n",
        encoding="utf-8",
    )
    (tmp_path / "docker-compose.yaml").write_text(
        "services:\n  web:\n    image: app:${CE_TEST_FROM_DOTENV}\n",
        encoding="utf-8",
    )
    assert main([]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "super-secret-from-dotenv" not in captured.err


def test_default_not_required(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CE_TEST_DEFAULT_A", raising=False)
    monkeypatch.delenv("CE_TEST_DEFAULT_B", raising=False)
    (tmp_path / "compose.yml").write_text(
        "services:\n"
        "  web:\n"
        "    image: app:${CE_TEST_DEFAULT_A:-latest}\n"
        "    command: echo ${CE_TEST_DEFAULT_B-other}\n",
        encoding="utf-8",
    )
    assert main(["-f", "compose.yml"]) == 0
    assert capsys.readouterr().out == ""


def test_var_without_default_still_required_if_also_defaulted(
    tmp_path: Path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CE_TEST_BOTH", raising=False)
    (tmp_path / "compose.yml").write_text(
        "services:\n"
        "  web:\n"
        "    image: app:${CE_TEST_BOTH:-dev}\n"
        "    command: echo ${CE_TEST_BOTH}\n",
        encoding="utf-8",
    )
    assert main(["-f", "compose.yml"]) == 1
    assert capsys.readouterr().out == "CE_TEST_BOTH\n"


def test_multiple_files(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CE_TEST_ONE", "present")
    monkeypatch.delenv("CE_TEST_TWO", raising=False)
    (tmp_path / "base.yml").write_text(
        "services:\n  web:\n    image: app:${CE_TEST_ONE}\n",
        encoding="utf-8",
    )
    (tmp_path / "override.yml").write_text(
        "services:\n  web:\n    command: echo ${CE_TEST_TWO}\n",
        encoding="utf-8",
    )
    assert main(["-f", "base.yml", "-f", "override.yml", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "missing": ["CE_TEST_TWO"],
        "checked": 2,
        "files": ["base.yml", "override.yml"],
    }
    assert "present" not in json.dumps(payload)


def test_dollar_dollar_escape(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("CE_TEST_REAL", raising=False)
    (tmp_path / "compose.yml").write_text(
        "services:\n"
        "  web:\n"
        "    image: app:${CE_TEST_REAL}\n"
        '    command: "echo $$HOME $${ALSO_IGNORED}"\n',
        encoding="utf-8",
    )
    assert main(["-f", "compose.yml"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "CE_TEST_REAL\n"
    assert "HOME" not in captured.out
    assert "ALSO_IGNORED" not in captured.out


def test_only_escaped_dollars_pass(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("ALSO_IGNORED", raising=False)
    (tmp_path / "compose.yml").write_text(
        'services:\n  web:\n    command: "echo $$HOME $${ALSO_IGNORED}"\n',
        encoding="utf-8",
    )
    assert main(["-f", "compose.yml"]) == 0
    assert capsys.readouterr().out == ""


def test_env_file_satisfies_passthrough(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CE_TEST_TOKEN", raising=False)
    monkeypatch.delenv("CE_TEST_OTHER", raising=False)
    (tmp_path / "app.env").write_text(
        "CE_TEST_TOKEN=do-not-print-this\n",
        encoding="utf-8",
    )
    (tmp_path / "compose.yml").write_text(
        "services:\n"
        "  web:\n"
        "    image: app\n"
        "    env_file:\n"
        "      - path: app.env\n"
        "    environment:\n"
        "      CE_TEST_TOKEN:\n"
        "      LITERAL: kept\n"
        "      CE_TEST_OTHER: ${CE_TEST_OTHER}\n",
        encoding="utf-8",
    )
    assert main(["-f", "compose.yml"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "CE_TEST_OTHER\n"
    assert "do-not-print-this" not in captured.out
    assert "do-not-print-this" not in captured.err
    assert "LITERAL" not in captured.out


def test_comments_are_not_references(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "compose.yml").write_text(
        "services:\n  web:\n    image: nginx\n# ${CE_TEST_COMMENTED}\n",
        encoding="utf-8",
    )
    assert main(["-f", "compose.yml"]) == 0
    assert capsys.readouterr().out == ""


def test_builtin_is_ignored(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("COMPOSE_PROJECT_NAME", raising=False)
    (tmp_path / "compose.yml").write_text(
        "services:\n  web:\n    container_name: ${COMPOSE_PROJECT_NAME}-web\n",
        encoding="utf-8",
    )
    assert main(["-f", "compose.yml", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["missing"] == []
    assert payload["checked"] == 0


def test_strict_reports_default_only(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CE_TEST_OPT", raising=False)
    (tmp_path / "compose.yml").write_text(
        "services:\n  web:\n    image: app:${CE_TEST_OPT:-local}\n",
        encoding="utf-8",
    )
    assert main(["-f", "compose.yml", "--strict"]) == 1
    assert capsys.readouterr().out == "CE_TEST_OPT\n"


def test_env_file_flag_replaces_dotenv(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CE_TEST_WHICH", raising=False)
    (tmp_path / ".env").write_text("CE_TEST_WHICH=from-dotenv\n", encoding="utf-8")
    (tmp_path / "other.env").write_text("# no CE_TEST_WHICH here\n", encoding="utf-8")
    (tmp_path / "compose.yml").write_text(
        "services:\n  web:\n    image: app:${CE_TEST_WHICH}\n",
        encoding="utf-8",
    )
    assert main(["-f", "compose.yml", "--env-file", "other.env"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "CE_TEST_WHICH\n"
    assert "from-dotenv" not in captured.out


def test_bad_yaml_exits_2(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "compose.yml").write_text("services: [\n", encoding="utf-8")
    assert main(["-f", "compose.yml"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "invalid YAML" in captured.err
    assert "compose.yml" in captured.err


def test_missing_compose_file_exits_2(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no compose file found" in captured.err


def test_unknown_flag_exits_2(capsys):
    assert main(["--not-a-flag"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err != ""


def test_sorted_missing_names(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CE_TEST_ZEBRA", raising=False)
    monkeypatch.delenv("CE_TEST_ALPHA", raising=False)
    (tmp_path / "compose.yml").write_text(
        "services:\n  web:\n    image: ${CE_TEST_ZEBRA}:${CE_TEST_ALPHA}\n",
        encoding="utf-8",
    )
    assert main(["-f", "compose.yml"]) == 1
    assert capsys.readouterr().out == "CE_TEST_ALPHA\nCE_TEST_ZEBRA\n"


def test_list_passthrough_without_equals(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CE_TEST_PASS", raising=False)
    (tmp_path / "compose.yml").write_text(
        "services:\n"
        "  web:\n"
        "    image: nginx\n"
        "    environment:\n"
        "      - CE_TEST_PASS\n"
        "      - LITERAL=value\n",
        encoding="utf-8",
    )
    assert main(["-f", "compose.yml"]) == 1
    assert capsys.readouterr().out == "CE_TEST_PASS\n"
