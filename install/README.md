# Install

DevSpan is one global store (`DEVSPAN_HOME`, default `~/.devspan`). The `--directory` argument is where this server's code lives. The running server reads that store no matter which workspace is open, so other repos do not need this checkout added to them.

**Start the server.** Upsert the block below into each enabled host.

**Use the server.** The router body that ships is `.cursor/rules/devspan-router.mdc` (`alwaysApply: true`). Place it only when a user-scoped instruction file uses the `.mdc` extension. This product does not ship a markdown router. A platform with no matching body still gets the server block. Do not invent one.

The host list is `platforms.yaml`, next to `nexus.md` on the install root. This page does not name hosts or their files. The stored definition is that home.

A project server file committed in this checkout only starts when this repo is the open workspace. The user-scoped file from the definition is what makes the server available in other workspaces.

Behind an SSL-inspecting proxy, add `--system-certs` as the first argument, or set `UV_SYSTEM_CERTS=1` on `env`.

## When there is no environment file

Do not edit user-global server config. Do not copy the router into a user rules directory. Do not write a project instruction file.

Recording the host this agent is running in is how a machine gets its first `enabled` name. Look up that one host's server file, key, format, and where it loads user-global instructions. Write them into `platforms.yaml`. Set `enabled` to that one name. Do not search the profile for other hosts. Then run the pass below for that name only.

## Server block

Replace the checkout path with this repo.

```yaml
command: uv
args:
  - run
  - --directory
  - /path/to/dev-span
  - devspan
```

When `format` is `json`, write that as an object under the definition's `key`. When `format` is `toml`, write it as a table under that key.

## Pass

Read `platforms.yaml`.

For each name in `enabled`:

- No stored definition: look up that host's real server file, key, format, and user-global instruction location. Write them under `platforms`. Do not paste paths from memory. Then continue.
- Server: for each `server` entry, open `path` and upsert the block under `key`, serialized as `format`. Leave every other key in that file alone.
- Router: for each `instructions` entry with `scope: user` whose `path` ends in `.mdc`, write `devspan-router.mdc` into that file's directory. The body is `.cursor/rules/devspan-router.mdc` in this repo. Copy it as it is. Do not replace another product's file.

Skip a definition you cannot apply, say which one, and continue with the other names.

## Maintenance

Add, remove, and a moved checkout all run the pass above.

**Add.** Put the name on `enabled`. Run this pass, and the same pass for each other public product already installed. The pass writes a missing definition before it upserts. This product does not write a project protocol.

**Remove.** Take the name off `enabled`. Dry-run first. For that name's server entries, list this product's key under `key`. If a user-scoped instruction path ends in `.mdc`, also list `devspan-router.mdc` in that file's directory. Write nothing. Every other key in the host file stays. On the real remove, delete only those keys and that router file.

**Path refresh.** The checkout moved. Run the pass again so this product's block uses the current path. Upsert this product's key. Leave every other key alone.
