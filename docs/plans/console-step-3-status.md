# Console step 3 — status

Where the work on [step 3 of the console](console-step-3.md) stands (Inventory: inventory endpoints of protocol §8, snapshot storage, processing, attachment, UI), and what comes next. Updated on 2026-11-12.

Resume on another machine and working agreement: see [step 1 status](console-step-1-status.md). Inventories are processed by the Compose `worker` service (`messenger:consume ingest`): after a code change, `make worker-restart`; its output with `make worker-logs`.

## Delivered (committed on `main`, not pushed yet)

| Commit | Content |
|---|---|
| `.github` `1df743c` | Lot 1, protocol: `host` subject (OS packages of the host), schema, example, `validate.py` |
| `console` `6c9a81a` | Lot 2, foundations: Doctrine Messenger transports `ingest` and `failed`, `worker` service, `GetAgentContext` contract, problems `scope_violation` / `missing_snapshots` / `digest_mismatch`, body limit per route (20 MiB for a snapshot, Caddy too) |
| `console` `4c837f3` | Lot 3, domain: inventory run, snapshot blob, host inventory, application, container image, snapshot record, packages; migration with the same-team trigger |
| `console` `69a9dab` | Lot 4, agent API: manifest, snapshot upload (streamed gzip, 200 MB cap, digest and format checks), complete, scope guard, `agent_pending`, audit |
| `console` `ad52647` | Lot 5, processing in the `ingest` queue: CycloneDX packages once per blob, applications and images, `gone`, automatic attachment, `make inventory-maintain` (retention, orphan blobs, stale inventories); no `serialNumber` in the SBOM profile |
| `console` `99285a2` | Lot 6, UI: team Applications section (not attached first), project Applications tab, application page (Attach / Move / Detach), host page (facts, OS packages), image page; `TEAM_GUEST` visibility |
| `console` + `.github` (lot 7) | Fake agent inventory (`make fleet-fake-agent a=inventory`, and after a `SCAN_NOW`), decisions 35–43 in `cadrage.md`, `design.md`, this plan and status, console `CLAUDE.md` |
| `console` (lot 8) | Inventory figures on the team overview (lazy frame `/teams/{t}/frames/inventory`); inventory history on the application and host pages (`ListInventoryHistory`, changed against the previous record of the same subject) |

## Decisions taken after the plan

Recorded in `cadrage.md` (decisions 35 to 43) and `design.md`:

- **No `serialNumber`** in the CycloneDX profile (§8.5): it would change the digest of unchanged content.
- An application turns `gone` only when the agent that reported it last no longer does: several agents on one host do not remove each other's applications.
- Detaching an application that is not attached is a no-op (marking it as decided by a human would otherwise need no permission).
- A host enrolled but not inventoried yet shows an empty page to a member instead of a 404.
- The sidebar's Applications entry is shown to a `TEAM_GUEST` too: it is their way to the applications of their projects.
- The audit middleware ignores the send-only pass of an asynchronous command: one entry per processed inventory, written by the worker.

## Checked end to end

`make fleet-fake-agent a=inventory name=…` against the dev stack: the inventory goes through the `ingest` queue, the worker marks it `processed`, the Compose service, its image and their packages are stored; a second identical inventory uploads no snapshot.

## Next task: browser check, then step 4

1. Check the Inventory pages in a real browser (`admin@depverify.localhost`): inventory figures on the team overview, Applications (team and project), application page with its Attach dialog and history, host page from the Hosts list, image page; then `SCAN_NOW` from the agent page while `make fleet-fake-agent a='run --polls=10'` runs (the inventory follows the poll). A host-mode fake agent (`enroll --mode=host`) sends the OS packages and a path application.
2. Step 4, Vulnerability and Exposure: OSV / endoflife.date / KEV / EPSS sync and matching over the normalized inventory (`InventoryProcessed` event).

## Backlog

- Diff between inventories and drift detection; Git, CI and upload sources; `embedded` and `ecs` modes.
- From step 1: clean up the old Compose volumes `console_*`.
