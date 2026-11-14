<p align="center"><img src="https://raw.githubusercontent.com/DependencyVerifier/.github/main/docs/brand/logo-mark.svg" width="72" height="72" alt="DependencyVerifier"></p>

<h3 align="center">What really runs in production, and what threatens it.</h3>

DependencyVerifier is an open source, self-hosted monitor of the dependencies and runtimes **actually deployed** on your servers and containers. An agent inventories each machine (OS packages, PHP, Node, Composer and npm dependencies, Docker images) and reports over an outbound-only, signed connection; the console matches everything against OSV, CISA KEV, EPSS and endoflife.date and notifies each project by its own rules.

| Repository | What | License |
|---|---|---|
| [console](https://github.com/DependencyVerifier/console) | Self-hosted web console (Symfony, PostgreSQL) | AGPL-3.0 |
| [agent](https://github.com/DependencyVerifier/agent) | Lightweight agent (Rust, static binary) | Apache-2.0 |
| [agent-image](https://github.com/DependencyVerifier/agent-image) | Container image `ghcr.io/dependencyverifier/agent` | Apache-2.0 |
| [.github](https://github.com/DependencyVerifier/.github) | Specification, UI charter, brand assets | — |

> Status: 1.0. Getting started: [rolling out DependencyVerifier on your fleet](https://github.com/DependencyVerifier/console/blob/main/GUIDE.md).
