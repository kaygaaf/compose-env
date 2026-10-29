# compose-env

Checks docker-compose files for missing env vars.

It finds `${VAR}` and `$VAR` references, then tells you which ones are unset. It does not print secret values.

Handy when you self-host with Coolify, Portainer, or plain Compose and something fails at boot because an env file is incomplete.

## Status

Just starting. Working on a small CLI.

## Support

If this helps: [ko-fi.com/kayorama](https://ko-fi.com/kayorama)








