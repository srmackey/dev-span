# Security

## Reporting

Report a vulnerability privately with a GitHub Security Advisory on this repository. Do not open a public issue for a bug that would write outside the store, or delete entities the caller did not name.

## Trust boundary

- Transport is stdio. The host starts a local process as the user who launched it.
- The process reads and writes markdown under `DEVSPAN_HOME`, or `~/.devspan` when that is unset. It also writes a derived SQLite index there.
- It does not fetch URLs and it does not take a credential.
- `delete_entity` removes an entity, its documents, and the links that pointed at it.
