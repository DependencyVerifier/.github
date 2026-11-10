# DependencyVerifier — specification and brand

Shared documentation of [DependencyVerifier](https://github.com/DependencyVerifier), and the organization profile.

- [`docs/cadrage.md`](docs/cadrage.md): specification (French), the living source of truth.
- [`docs/design.md`](docs/design.md): UI charter of the console.
- [`docs/protocol.md`](docs/protocol.md): agent ↔ console protocol v1 (normative), with JSON Schemas, examples and test vectors in [`docs/protocol/`](docs/protocol).
- [`docs/plans/`](docs/plans): implementation plans and where they stand ([`console-step-1-status.md`](docs/plans/console-step-1-status.md): progress, decisions since the plan, next tasks).
- [`docs/brand/`](docs/brand): logo (SVG), favicon, og:image and GitHub social preview images.
- [`scripts/workspace.sh`](scripts/workspace.sh): clones or updates every repository over SSH into one folder, then installs them (console stack, agent build, agent image). On a new machine, clone this repository into the workspace folder, then run it.
- [`governance/`](governance): who may push where; ruleset protecting `main` and the script that applies it.
- [`profile/README.md`](profile/README.md): the page shown on github.com/DependencyVerifier.
