# Console step 4 — status

Where the work on [step 4 of the console](console-step-4.md) stands (Vulnerability and Exposure: public sources, local matching, findings, risk acceptance), and what comes next. Updated on 2026-11-12.

Resume on another machine and working agreement: see [step 1 status](console-step-1-status.md). The Compose `worker` service consumes `ingest matching feeds`: after a code change `make worker-restart`, after a change of `compose.yaml` `docker compose up -d worker`.

## Delivered (committed on `main`, not pushed yet)

| Commit | Content |
|---|---|
| `.github` `2d0d32b` | Protocol §8.5: `distro` and `upstream` qualifiers of OS packages |
| `console` `30eb8a5` | The fake agent sends them |
| `console` `98a784b` | Version ordering per ecosystem (Composer, SemVer, dpkg, apk, rpm), OSV ranges, CVSS 3.x, OSV coordinates of a purl |
| `console` `d126f0f` | Watched packages, OSV sync by package name, CISA KEV, FIRST EPSS; queues `feeds` and `matching`; `make vuln-sync` |
| `console` `85811dd` | End of life cycles (endoflife.date), latest releases of direct dependencies (Packagist, npm), matching (`AssessSubjects`), findings and their coalesced refresh; `make eol-sync`, `make findings-refresh` |
| `console` (lot 6) | Risk acceptance (justification, expiry within a year, revocation), findings tables on the application and host pages, finding page |
| `console` + `.github` (lot 7) | Decisions 44–53 in `cadrage.md`, `design.md`, this plan and status, console `CLAUDE.md` |

## Decisions taken after the plan

Recorded in `cadrage.md` (decisions 44 to 53):

- OSV through the **targeted API**, not the full exports: osv.dev only ever receives package names.
- No cron bundle yet (`lexik/cron-file-generator-bundle` does not install on Symfony 8.1 as is: its extension loads XML service files, a loader Symfony 8 removed); the commands and their `make` targets only queue the work.
- One end of life finding **per cycle**, not per product.
- A refresh request already pending for a team adds nothing (`TeamExposure`): a sync of hundreds of advisories computes each team once.
- Risk acceptance on a host or an application not attached: `host.approve` (a project permission means nothing without a project). Their findings are seen by whom sees every project of the team, never a `TEAM_GUEST`.
- An acceptance expires on its own (the finding counts as open again): no expiry task.
- The OSV records of a sync are fetched 50 at a time, concurrently.

## Checked end to end

`make fleet-fake-agent a=inventory` against the dev stack with the real sources: 8 watched packages, 732 advisories, 209 findings on the demo application (curl, glibc, openssl, axios, twig, lodash, and 5 outdated direct dependencies; the fake agent ships old versions on purpose). Functional tests drive the same chain with recorded answers (`tests/Vulnerability/Fixtures/feeds`).

## Next task: see step 5

Step 5 (dashboards) is delivered: see [its status](console-step-5-status.md).

## Backlog

- RHEL advisories (OSV names them by product stream); RPM packages of RHEL are not matched yet.
- Advisory page (summary, references, applications affected in the team).
- Cron bundle: `lexik/cron-file-generator-bundle` once it supports Symfony 8 (or a patch).
- Offline mode (import of the sources), roadmap §11.
