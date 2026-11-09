# DependencyVerifier

Open source, self-hosted monitoring of **what really runs in production** (runtimes, Composer/npm dependencies, OS packages, Docker images), continuously matched against vulnerability (OSV, KEV, EPSS) and end-of-life (endoflife.date) data, with per-project notifications.

- **Console** (`console/`, AGPL-3.0): multi-team Symfony web app, inventory store, matching engine, notifications.
- **Agent** (`agent/`, Apache-2.0): lightweight Rust binary on each server / Compose project; inventories and reports over an **outbound-only**, signed connection.
- **Agent image** (`agent-image` repository): Dockerfile and Compose example of `ghcr.io/dependencyverifier/agent`, built from the `agent` repository. The console keeps its own Docker configuration (`Dockerfile`, `compose*.yaml`).

Differentiator: the source of truth is the **production machine**, not the repo or CI (third-party hosts, repo vs. deployed drift, runtimes and OS packages, multi-team).

## Full specification

**`docs/cadrage.md` (French, in this repository) is the living source of truth.** Read the relevant section before designing or implementing anything; update it when a decision changes. UI charter: `docs/design.md`. Agent ↔ console protocol v1 (normative, English): `docs/protocol.md`, machine-readable parts in `docs/protocol/` (schemas, examples, test vectors), checked by `docs/protocol/validate.py` in CI. Any protocol change updates the spec, schemas and examples together.

| § | Topic |
|---|---|
| 2 | Vision, differentiator, agent security principles |
| 3 | **Decisions table** (licences, stack, auth, design, modes, quotas…) |
| 4 | Architecture overview |
| 5 / 5bis / 5ter | Data model, hosts ↔ agents ↔ projects, quotas & instance limits |
| 6 | Agent: distribution, install trust chain, enrollment, reusable tokens, signed protocol, orders, collected data, privileges |
| 6bis | Containers: image-by-digest, modes `host` / `container` / `embedded` / `ecs`, `AGENT_SCOPE`, `dev.depverify.*` labels |
| 7 / 7bis | Console security (auth, passkeys, audit) / permissions (roles, catalogue, guard rules, Symfony implementation) |
| 8 | Analysis engine: sources, matching, notifications |
| 9 / 9bis | Stack / sizing (200 → 2 000 agents) |
| 10 / 11 / 12 | MVP scope / roadmap / open questions |

## Non-negotiable principles

- Agent: outbound HTTPS only, no open port; Ed25519-signed requests; console key **pinned** at install; human approval of every agent (only exception: approved reusable enrollment token); **closed order catalogue, never arbitrary shell commands**.
- The analysis engine, data model and notifications **never depend on the agent**: they consume a normalized inventory (CycloneDX SBOM + runtime facts) from any `InventorySource`.
- **UUID v7 for every entity**; names/slugs are display only.
- Secrets never readable back (stored hashed, shown once); secrets at rest encrypted (AES-256-GCM, master key outside the DB).
- Audit log is **append-only** (PostgreSQL triggers), never stores request bodies.
- Authorization is centralized (voters test **permissions**, never roles); listings are scope-filtered; quotas are enforced in domain services (strict blocking).
- Auth: email + password then second factor (TOTP, else email code); passkey optional; invitation-only accounts; no telemetry, no external UI resources.

## Repositories (GitHub organization `DependencyVerifier`)

| Repository | Content |
|---|---|
| [`.github`](https://github.com/DependencyVerifier/.github) (this one) | `docs/cadrage.md` (spec, FR), `docs/design.md` (UI charter), `docs/protocol.md` (agent protocol v1), `docs/brand/` (logo, favicon, og:image and GitHub social images), organization profile (`profile/README.md`) |
| [`console`](https://github.com/DependencyVerifier/console) | Symfony 8.x + PHP 8.5 (dunglas/symfony-docker, FrankenPHP), PostgreSQL, Twig + Symfony UX, Reprise + Vite (TypeScript only), Tailwind v4, UX Toolkit shadcn. DDD contexts (`Shared\`, `Identity\`, `Organization\`, `Fleet\`, `Inventory\`, `Vulnerability\`, `Exposure\`, `Notification\`, `Audit\`), CQRS on 3 Messenger buses, `Makefile`. Submodule `assets/romain-millan-tag` (footer signature) |
| [`agent`](https://github.com/DependencyVerifier/agent) | Rust crate `depverify-agent` (static musl, rustls) |
| [`agent-image`](https://github.com/DependencyVerifier/agent-image) | Dockerfile of `ghcr.io/dependencyverifier/agent` (built from `agent`) + Compose example |

Each repository has its own `CLAUDE.md` with stack details and commands. Locally, clone them side by side in one folder.

## Conventions

- **Language: English everywhere** (code, comments, commits, READMEs, UI strings source). The spec in `docs/cadrage.md` stays in French.
- **Commits**: subject line only, `type: Capitalized imperative subject` (`feat`, `fix`, `chore`, `doc`, `refactor`, `test`), no body, no trailer, no `Co-Authored-By`.
- **Everything runs in Docker**: no PHP/Node/Rust tooling assumed on the host.
  - Console: `make …` from `console/` (`make help`), local URL **https://console.depverify.localhost**; JS packages with `docker compose exec node yarn …`, **never npm**. Run `make qa` before committing console code.
  - Agent: `docker run --rm -v "$PWD":/work -w /work rust:1 cargo …` from the agent repository.
- PHP: Symfony String `u()` instead of native string functions; `SluggerInterface` for slugs; `#[AutoconfigureTag]` without explicit name.
- Git submodules: clone with `--recurse-submodules` (or `make submodules` in `console/`).
- Never commit dependencies or build output (`node_modules/`, `public/build/`, `target/`): ignored in each repository.
- **Only organization owners push to `main`**; everyone else opens a pull request (see `governance/` in the `.github` repository).
- Never commit without being asked.

## MVP scope (summary)

Accounts + 2FA + optional passkeys, notification-only accounts, invitations, teams with quotas, team/project roles; full agent enrollment (single + reusable tokens); inventory every 6 h + on demand + on image change, 90-day history; Linux/systemd agent (OS packages, PHP/Composer, Node, runtimes); `container` mode with read-only socket proxy; OSV + endoflife.date + KEV + EPSS sync and matching; dashboards; email + webhook notifications; append-only audit; signed orders `SCAN_NOW`, `SET_CONFIG`.

**Out of MVP**: public API / API tokens, SSO, Fargate (`ecs`) collector, `embedded` mode, registry access, Kubernetes, Windows, ticket/PR creation, `UPGRADE_AGENT` / `ROTATE_KEY`, air-gap mode.
