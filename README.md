# compose-env

Checks docker-compose files for missing environment variables.

It finds `${VAR}` and `$VAR` references, then tells you which ones are unset. It does not print secret values.

Handy when you self-host with Coolify, Portainer, or plain Compose and something fails at boot because an env file is incomplete.

## Install

Requires Python 3.10 or newer.

```bash
pipx install compose-env
```

```bash
pip install compose-env
```

From a checkout of this repo:

```bash
pip install .
```

## Usage

In a directory that has a compose file:

```bash
compose-env
```

With no `-f`, it checks every file that exists among `docker-compose.yml`, `docker-compose.yaml`, `compose.yml`, and `compose.yaml`.

```bash
compose-env -f compose.yml
compose-env -f compose.yml -f compose.override.yml
compose-env --env-file .env.production
compose-env --json
compose-env --strict
```

A name is required when the file uses `$VAR` or `${VAR}` and there is no default. `${VAR:-default}` and `${VAR-default}` are not required. `--strict` also reports names that only show up with a default.

`$$` is a literal dollar sign, same as in Compose, so `$$VAR` is not a reference.

Values are taken from the process environment, then from `--env-file`. If you omit `--env-file`, `.env` in the current directory is used when it is present. Lines are `KEY=VALUE` (a colon separator works too). Blank lines and `#` comments are ignored. An empty value still counts as set.

Keys in a service `env_file` are treated as set when that file exists. Paths are relative to the compose file. Missing `env_file` paths are skipped.

Under `environment`, a name with no value (`FOO:` or `- FOO`) is required. `FOO: bar` is a literal and is not.

Compose control variables such as `COMPOSE_PROJECT_NAME` are ignored.

Missing names are printed one per line. Nothing is printed when every required name is set. `--json` prints one object:

```json
{"missing": ["DATABASE_URL"], "checked": 3, "files": ["compose.yml"]}
```

`checked` is how many required names were looked up. `files` is the compose files that were read. Set values are never printed.

## Exit codes

- `0` every required variable is set
- `1` one or more required variables are missing
- `2` usage or parse error (missing file, bad YAML, unknown flag)

## Support

If this helps: [ko-fi.com/kayorama](https://ko-fi.com/kayorama)
