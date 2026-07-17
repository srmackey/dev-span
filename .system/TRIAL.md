# ContextForge Trial — What to Watch For

Purpose: a ~2-week trial to prove ContextForge earns daily use *before* building
anything else. This file is the rubric and the log. Fill in the log at the bottom
as things happen — don't reconstruct from memory at the end.

The three questions: **(1) is it working?** **(2) is it saving tokens?**
**(3) what friction shows up, and which deferred feature does it justify?**

---

## How to instrument (do this first)

You can't judge from vibes alone. The system now provides built-in persistent
instrumentation (see evolution.md Round 9).

1. **Persistent logs are on by default.** Every run writes structured events to
   `~/.contextforge/logs/contextforge.log` (rotating, ~15 MB total). Events include:
   - `pack:start` / `pack:done` (links, governance count, dropped, chars, elapsed)
   - `resolve:narrowed` (DEBUG) with per-subtopic bm25 scores + dropped lists
   - entity:created, task:linked, governance:attached, context:upsert, workspace:bound,
     ref:resolved, suggest:links, always_include changes, etc.
2. **Repo-local / traveling logs (dev + dogfooding):** set
   `CONTEXTFORGE_DEV_LOG_DIR=.system/usage-logs` (or `CONTEXTFORGE_LOG_FILE=...`)
   inside this checkout. You will get events in **both** the normal home location
   *and* the extra file. This is how you make the data travel with the repo for
   evaluation "at home". See `.system/usage-logs/README.md` and `evolution.md` Round 9.
3. **Inside the MCP:** call `tail_logs(n=100)` (or higher) to pull recent lines directly.
   No need to hunt Cursor logs or set up redirection.
3. **Live verbosity:** `CONTEXTFORGE_LOG_LEVEL=DEBUG` (affects both stderr and the
   file) for full FTS scoring breakdowns during a session.
4. **Watch the `dropped` field** in every `get_task_pack` response (still the
   primary real-time signal).
5. **Keep the (human) log below.** One row per real task. The file log gives you the
   quantitative picture; this table gives the qualitative "did it help?" judgment.

---

## 1. Is it working?

"Working" = it gives the agent durable context it would **not** have had otherwise,
and you actually reach for it.

**The core test — the counterfactual:** for each load, ask *"would the agent have
known this from `@codebase` / the repo alone?"* If yes, it added nothing. The value
is **tribal knowledge that lives in no file** — the stuff you'd otherwise have typed
out by hand.

**Green signals (it's working):**
- [ ] The router rule fires on its own — you start a task and context shows up
      without you manually invoking a tool.
- [ ] A loaded note stopped the agent from making a wrong assumption it would have
      made cold (e.g. wrong auth flow, wrong local-setup step).
- [ ] You stopped re-typing the same explanation you used to give every session.
- [ ] `resolve_ref` maps your nickname ("the gateway") to the right entity.
- [ ] You update a note when reality changes — i.e. you *maintain* it without being
      nagged.

**Red signals (it's not):**
- [ ] You forget it exists for several days and don't miss it.
- [ ] The pack is full of stuff the agent already knew → no marginal value.
- [ ] A stale note **misled** the agent (worse than having no note).
- [ ] You spend more time feeding/maintaining it than it saves.
- [ ] You have to manually invoke it every time because the router never triggers.

---

## 2. Is it saving tokens?

Savings is a **counterfactual** — "fewer tokens than what I *would* have loaded."
You won't get an exact number from Cursor, so track the mechanism and proxies.

**Where the savings actually come from:**
- Not re-explaining tribal knowledge every new session (load a 200-token note vs.
  re-typing 200 tokens of prose each time).
- Loading a tight, targeted pack + **pointers** instead of pasting whole files or
  whole Confluence pages.
- Progressive disclosure: focus-mode drops low-relevance subtopics; you fetch the
  `dropped` ones only if they turn out to matter.
- Hydrating live data **narrowly** through the native MCPs (a ticket's status, not
  its entire body) instead of dumping it all in.

**Green signals (it's saving):**
- [ ] `get_task_pack(focus=True)` returns a tight bundle with a non-empty `dropped`
      list — and you rarely need to pull the dropped refs back.
- [ ] You paste fewer raw files / docs into chat than you used to.
- [ ] Across sessions you stop re-typing the same context.
- [ ] When you need live Jira/GitLab data, you fetch the narrow slice you need.

**Red signals (it's not — or it's costing tokens):**
- [ ] Packs **balloon**: an entity-level ref drags in every subtopic of a big
      component (the known "coarse pull" gap). `dropped` stays empty, pack is huge.
- [ ] You still paste docs by hand because the pack missed them.
- [ ] You load context you never actually use in the task.
- [ ] `focus=True` drops the subtopic you *did* need, so you re-fetch anyway (net
      churn, not savings).

> Rough A/B if you want a harder number: on 2–3 comparable tasks, do one cold and
> one with ContextForge, and eyeball context-window usage / how much you pasted.
> The pack-assembly log gives you the included-vs-dropped picture for free.

---

## 3. Friction → what it justifies building

The trial's real output: turn each *recurring* friction into evidence for one
deferred feature. **Rule: don't build on the first occurrence.** Log it; build only
when the same friction recurs ~3+ times. That's the whole point of running the trial
instead of building speculatively.

| Friction you observe | What it means | Deferred feature it justifies |
|---|---|---|
| You keep hand-linking the same MR ↔ ticket ↔ page; the agent re-discovers cross-refs each time | Manual edge capture doesn't scale | **Harvester** — auto-mine GitLab/Jira/Confluence cross-links |
| You created two notes for the same subject; nothing stopped you at create time | `resolve_ref` is read-side only; no create-time guard | **Create-side dedup/normalize gate** (normalize → exact → fuzzy → confirm, never auto-merge) |
| Packs are too big for large components even with `focus=True` | Relevance narrowing too coarse | Tune `per_entity_top_k` / `min_score` first; if still bad → better retrieval (see below) |
| `resolve_ref` / search misses an obvious match phrased differently | FTS is naïve (phrase-only) | **Semantic / vector search** (`sqlite-vec`) |
| You forget to invoke it / the router fires unreliably | Retrieval isn't automatic enough | Stronger always-on rule, or real MCP **Roots** integration |
| You're in a repo and still have to tell it which repo | Workspace detection is passive (`bind_workspace` is manual) | **Auto workspace→repo binding** / Roots |
| A note went stale and misled you | No refresh discipline beyond `list_stale_sources` | Staleness workflow / harvester refresh loop |
| You want a teammate to use the same context | `~/.contextforge/` is single-user | **In-repo packaging + team namespace** (spec Phase 3) |
| You need to relate two things and no entity type / edge fits | Fixed taxonomy can't express the relationship | **Generic typed node + edge model** (unlikely in 2 weeks — flag it if it happens) |

---

## Decision at the end of the trial

**Keep going if:** you reach for it unprompted, it answered at least a few times
with knowledge the agent couldn't have gotten cold, you maintained the notes, and
you can point to ≥1 clear "this saved me" moment.

**Kill / rethink if:** you kept forgetting it and didn't miss it, maintenance
outweighed value, or stale notes misled more than fresh ones helped.

Either way, the friction log tells you what to build *next* — backed by evidence,
not guesses.

---

## Running log

The running log — one row per real task ContextForge was used (or wanted) on — lives
in `TRIAL-log.md` next to this file. It is gitignored on purpose: real-task rows
naturally reference private work (ticket IDs, internal repo names), so they must not
be committable by accident. Keep this file as the rubric; record evidence there.

The unexercised-feature gaps — governance cascade, focus-mode / `dropped`, and the
router rule firing on its own — are tracked in [design.md → Roadmap](design.md)
(Known limitations + Near-term priorities). Record observations against those gaps
in the log as real work exercises them, rather than restating them here.
