# Console step 2 — status

Where the work on [step 2 of the console](console-step-2.md) stands (Fleet core: enrollment, signed agent API, orders), and what comes next. Updated on 2026-11-11.

Resume on another machine and working agreement: see [step 1 status](console-step-1-status.md). The dev agent signing key is in `console/.env.dev` (`APP_AGENT_SIGNING_KEY`); production needs its own (`openssl rand -base64 32`), never changed once agents are installed.

## Delivered (committed on `main`, not pushed yet)

| Commit | Content |
|---|---|
| `console` `8e49fb8` | Lot 1, foundations: `ext-sodium`, Ed25519 signer / verifier, RFC 8785 canonical JSON, `APP_AGENT_SIGNING_KEY` (fail-closed boot check), the two protocol test vectors reproduced byte for byte, `Agent` audit actor, Organization contracts (`GetTeamAccess`, `GetTeamQuota`, `FindTeamEnvironment`, `ListTeamEnvironments`), `QuotaUsageProvider` port, agent limiters |
| `console` `96623f4` | Lot 2, domain: enrollment token, host, agent, order aggregates; migration `Version20261111120000` (partial unique index: one live agent per key); Doctrine repositories |
| `console` `06349e3` | Lot 3, signed agent API: `POST /agent/v1/enrollments` (proof of possession, idempotent retry), stateless `agent` firewall verifying protocol §4.3 in order, `POST /agent/v1/poll`, nonces, problem documents, audit of refusals; `TeamContentEraser` (team deletion takes its fleet) and Fleet's `ProjectContentProbe` |
| `console` `e4dbf9a` | Lot 4, UI: team sections Hosts / Agents / Enrollment, token shown once with the Compose snippet, agent approval comparing the fingerprint, revocations, host deletion, `/admin/agents`, enforced `max_agents` / `max_reusable_enrollment_tokens` gauges; team deletion under the fleet lock (security review) |
| `console` `ec1c8c4` | Lot 5, orders: Scan now (1 / 5 min), Configure (`SET_CONFIG`, team minimum interval), agent page with its orders, `make fleet-maintain`; single-use token form without the reusable fields, stable list order |

| `console` `a7a99b2` | Fleet context in the console `CLAUDE.md` |
| `console` `dd948dd` | Dev fake agent: `make fleet-fake-agent` (enroll, poll, run), protocol v1 as the agent must speak it |

## Decisions taken after the plan

Recorded in `cadrage.md` (decisions 21 to 34) and `design.md`:

- An `inactive` agent silent 30 days more is **revoked**, not deleted (history and audit kept, same effect for the agent).
- Approval of a pending agent is refused only when the team is **over** its `maxAgents` (the agent already counts).
- A single-use token has nothing to set (1 hour, 1 agent); its usable state shows as "Active".
- A plain poll writes no audit entry; refusals of agent requests are audited outside any team scope (the claimed `keyid` is untrusted).
- `GET` on a POST-only `/agent/v1` route answers 400 `invalid_payload` (the router refuses the method before the firewall), still a problem document, never a redirect.

## Next task: browser check, then step 3

1. Check the Fleet pages in a real browser (`admin@depverify.localhost`): enrollment dialog (no sideways scroll), token list statuses, agent approval, agent page, Configure dialog. Drive a demo agent with `make fleet-fake-agent a='enroll --token=dvet_…'`, then `a='run --polls=10'`.
2. Step 3, Inventory: the 3 inventory endpoints of protocol §8 (manifest, snapshot upload, complete), CycloneDX storage, hosts ↔ projects links (a `TEAM_GUEST` then sees the hosts of its projects).

## Backlog

- `install.sh` and the minisign binary mirror, once the agent has a release.
- Notifications (pending agent, silent agent, auto-approved agent): with the Notification context.
- Long polling (`next_poll_in` stays 60 / 300 s).
- `embedded` and `ecs` modes, CloudScope.
- From step 1: clean up the old Compose volumes `console_*`.
