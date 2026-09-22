# Tools

Every tool sets `openWorldHint` false. Writes stay under `DEVSPAN_HOME` (default `~/.devspan`). None of these tools fetch the network.

| Kind | readOnlyHint | destructiveHint | idempotentHint |
|---|---|---|---|
| Read | true | false | true |
| Create | false | false | false |
| Write | false | false | true |
| Append | false | false | false |
| Delete | false | true | true |

| Tool | Kind | What it does | Side effects |
|---|---|---|---|
| `create_component` | Create | Create a component. Optional kind, aliases, uses, governance. | Writes the entity and its scaffold documents. |
| `create_repo` | Create | Create a repo. Optional parent component. | Writes the entity and its scaffold documents. |
| `create_task` | Create | Create a task. | Writes the entity and its scaffold documents. |
| `create_governance` | Create | Create a governance entity. | Writes the entity and its scaffold documents. |
| `list_components` | Read | List components. Optional kind filter. | Reads the store. |
| `list_repos` | Read | List repos. | Reads the store. |
| `list_tasks` | Read | List tasks. | Reads the store. |
| `list_governance_entities` | Read | List governance entities. | Reads the store. |
| `delete_entity` | Delete | Delete one entity. | Removes the entity, its documents, aliases, task links, governance links, uses-graph edges, and parent pointers. |
| `get_context` | Read | Read an entity or one document. | Reads the store. |
| `upsert_context` | Write | Create or overwrite one document. | Writes that markdown file. |
| `append_context` | Append | Append to one document, creating it if needed. | Writes that markdown file. |
| `delete_context` | Delete | Delete one document. The entity stays. | Removes that file. |
| `add_alias` | Write | Add a globally unique nickname. | Writes the alias. |
| `remove_alias` | Write | Remove a nickname. | Writes the alias index. |
| `resolve_ref` | Read | Fuzzy lookup by slug, alias, or name. | Reads the store. |
| `link_task` | Write | Link refs onto a task. | Writes the task's links. |
| `unlink_task` | Write | Remove refs from a task. | Writes the task's links. |
| `get_task_pack` | Read | Assemble the task pack. Focus mode is the default and returns `dropped` when it narrows. | Reads the store. |
| `suggest_task_links` | Read | Suggest links from the uses graph and search. | Reads the store. Does not write the links. |
| `add_governance` | Write | Attach a governance ref to a component, repo, or task. | Writes that link. |
| `remove_governance` | Write | Remove a governance link. | Writes that link. |
| `add_external_ref` | Write | Record a pointer (system, id, optional url) on a task. | Writes the pointer. Does not fetch it. |
| `remove_external_ref` | Write | Remove one pointer. | Writes the task. |
| `import_content` | Write | Store text the caller already fetched, with a source url. | Writes that document. Does not fetch. |
| `refresh_source` | Read | Return the stored source url so the caller can re-fetch. | Reads the store. |
| `list_stale_sources` | Read | List snapshots older than a time. | Reads the store. |
| `search` | Read | Full-text search. Optional type and limit. | Reads the index. |
| `get_config` | Read | Read always-include refs and workspace bindings. | Reads the store. |
| `add_always_include` | Write | Include a ref in every task pack. | Writes config. |
| `remove_always_include` | Write | Stop including a ref in every pack. | Writes config. |
| `bind_workspace` | Write | Bind a folder path to a repo slug. | Writes config. Does not read the folder's files. |
| `unbind_workspace` | Write | Remove a folder binding. | Writes config. |
| `get_current_workspace` | Read | Resolve a folder path to its repo. | Reads config. |
| `reindex` | Write | Rebuild the SQLite index from the markdown. | Rewrites the index. Does not edit the markdown. |
| `tail_logs` | Read | Recent lines from the store log. | Reads the log. |

A tool add, remove, or rename updates this file and `CHANGELOG.md` in the same change.
