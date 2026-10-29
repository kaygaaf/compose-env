"""Load Compose files and report environment variables that are unset."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import yaml

from compose_env.refs import iter_references

# Compose defines these itself (or gives them a default). A file may
# reference them without the user exporting a value.
COMPOSE_BUILTINS = frozenset(
    {
        "COMPOSE_PROJECT_NAME",
        "COMPOSE_FILE",
        "COMPOSE_PROFILES",
        "COMPOSE_CONVERT_WINDOWS_PATHS",
        "COMPOSE_PATH_SEPARATOR",
        "COMPOSE_IGNORE_ORPHANS",
        "COMPOSE_REMOVE_ORPHANS",
        "COMPOSE_PARALLEL_LIMIT",
        "COMPOSE_ANSI",
        "COMPOSE_STATUS_STDOUT",
        "COMPOSE_ENV_FILES",
        "COMPOSE_DISABLE_ENV_FILE",
        "COMPOSE_MENU",
        "COMPOSE_EXPERIMENTAL",
        "COMPOSE_PROGRESS",
    }
)

DEFAULT_COMPOSE_NAMES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)

_ENV_KEY = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|:)")
_VAR_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ComposeEnvError(Exception):
    """A usage or parse problem. The CLI exits 2."""


@dataclass(frozen=True)
class Report:
    missing: list[str]
    checked: int
    files: list[str]


class _Loader(yaml.SafeLoader):
    """Safe loader that keeps unknown Compose tags (``!reset``, ``!override``)."""


def _construct_unknown(loader: yaml.SafeLoader, _suffix: str, node: yaml.Node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


_Loader.add_multi_constructor("!", _construct_unknown)


def build_report(
    compose_args: list[str] | None,
    env_file_args: list[str] | None,
    *,
    cwd: Path,
    environ_keys: set[str],
    strict: bool = False,
) -> Report:
    """Return missing variable names for the given Compose files.

    ``environ_keys`` is the set of names already present in the process
    environment. Values are never read.
    """
    compose_files = _compose_files(compose_args, cwd)
    required: set[str] = set()
    defaulted: set[str] = set()
    service_env_files: list[Path] = []

    for display, path in compose_files:
        for doc in _load_yaml(display, path):
            _scan_node(doc, required, defaulted)
            _scan_service_env(doc, path.parent, required, service_env_files)

    if strict:
        needed = (required | defaulted) - COMPOSE_BUILTINS
    else:
        needed = required - COMPOSE_BUILTINS

    provided = set(environ_keys)
    for display, path in _dotenv_files(env_file_args, cwd):
        provided.update(_read_env_keys(display, path, missing_ok=False))
    for path in service_env_files:
        provided.update(_read_env_keys(str(path), path, missing_ok=True))

    missing = sorted(needed - provided)
    return Report(
        missing=missing,
        checked=len(needed),
        files=[display for display, _path in compose_files],
    )


def _compose_files(
    compose_args: list[str] | None, cwd: Path
) -> list[tuple[str, Path]]:
    if compose_args:
        files: list[tuple[str, Path]] = []
        for arg in compose_args:
            path = _resolve(cwd, arg)
            if not path.is_file():
                raise ComposeEnvError(f"compose file not found: {arg}")
            files.append((arg, path))
        return files

    found = [
        (name, cwd / name)
        for name in DEFAULT_COMPOSE_NAMES
        if (cwd / name).is_file()
    ]
    if not found:
        names = ", ".join(DEFAULT_COMPOSE_NAMES)
        raise ComposeEnvError(f"no compose file found (looked for {names})")
    return found


def _dotenv_files(
    env_file_args: list[str] | None, cwd: Path
) -> list[tuple[str, Path]]:
    if env_file_args:
        files: list[tuple[str, Path]] = []
        for arg in env_file_args:
            path = _resolve(cwd, arg)
            if not path.is_file():
                raise ComposeEnvError(f"env file not found: {arg}")
            files.append((arg, path))
        return files

    default = cwd / ".env"
    if default.is_file():
        return [(".env", default)]
    return []


def _resolve(cwd: Path, arg: str) -> Path:
    path = Path(arg)
    if path.is_absolute():
        return path
    return cwd / path


def _load_yaml(display: str, path: Path) -> list:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ComposeEnvError(f"cannot read {display}: {exc.strerror}") from exc
    except UnicodeError as exc:
        raise ComposeEnvError(f"cannot read {display}: {exc}") from exc
    try:
        return list(yaml.load_all(text, Loader=_Loader))
    except yaml.YAMLError as exc:
        problem = getattr(exc, "problem", None) or "parse error"
        raise ComposeEnvError(f"invalid YAML in {display}: {problem}") from exc


def _scan_node(node, required: set[str], defaulted: set[str]) -> None:
    if isinstance(node, str):
        for name, has_default in iter_references(node):
            if has_default:
                defaulted.add(name)
            else:
                required.add(name)
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                _scan_node(key, required, defaulted)
            _scan_node(value, required, defaulted)
        return
    if isinstance(node, list):
        for item in node:
            _scan_node(item, required, defaulted)


def _scan_service_env(
    doc, compose_dir: Path, required: set[str], env_paths: list[Path]
) -> None:
    if not isinstance(doc, dict):
        return
    services = doc.get("services")
    if not isinstance(services, dict):
        return
    for spec in services.values():
        if not isinstance(spec, dict):
            continue
        _passthrough_names(spec.get("environment"), required)
        env_paths.extend(_env_file_paths(spec.get("env_file"), compose_dir))


def _passthrough_names(node, required: set[str]) -> None:
    """Names listed under ``environment`` with no value must come from outside."""
    if isinstance(node, dict):
        for key, value in node.items():
            if value is None and isinstance(key, str) and _VAR_NAME.fullmatch(key):
                required.add(key)
        return
    if isinstance(node, str):
        items = [node]
    elif isinstance(node, list):
        items = node
    else:
        return
    for item in items:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if "=" in name or ":" in name:
            continue
        if _VAR_NAME.fullmatch(name):
            required.add(name)


def _env_file_paths(node, compose_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for raw in _env_file_strings(node):
        if "$" in raw:
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = compose_dir / path
        paths.append(path)
    return paths


def _env_file_strings(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, list):
        found: list[str] = []
        for item in node:
            if isinstance(item, str):
                found.append(item)
            elif isinstance(item, dict):
                raw = item.get("path")
                if isinstance(raw, str):
                    found.append(raw)
        return found
    if isinstance(node, dict):
        raw = node.get("path")
        if isinstance(raw, str):
            return [raw]
    return []


def _read_env_keys(display: str, path: Path, *, missing_ok: bool) -> set[str]:
    """Return assignment keys. Values are discarded and never stored."""
    if not path.is_file():
        if missing_ok:
            return set()
        raise ComposeEnvError(f"env file not found: {display}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ComposeEnvError(f"cannot read {display}: {exc.strerror}") from exc
    except UnicodeError as exc:
        raise ComposeEnvError(f"cannot read {display}: {exc}") from exc

    keys: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ENV_KEY.match(stripped)
        if match:
            keys.add(match.group(1))
    return keys
