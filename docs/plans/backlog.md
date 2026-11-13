# Backlog

Work set aside, to pick up later. Each item points to its decisions in `cadrage.md` when there are some.

## Console

- **Step 1b: passkeys** (WebAuthn, optional, MVP §10.1). Library to choose (cadrage §12: Symfony support if any,
  else `web-auth/webauthn-framework`); a passkey as a sign-in method and as a second factor, enrolled from Account
  security, revocable; audited like the other factors.
- Cron bundle (`lexik/cron-file-generator-bundle` once it supports Symfony 8), wired to the existing `make` targets.
- Component matrix of an environment (which version runs on which host, §5bis).
- RHEL advisories (OSV names them by product, decision 45).
- Page of an advisory.
- Offline mode (§11).
- Charts redrawn on a theme switch without reload.
- Notifications: Slack, Teams and Discord channels; role raised when a promoted recipient accepts a team invitation;
  recipients out of `maxMembers`; a stored notification-only flag.

## Agent

- The release key embedded in the agent, for `UPGRADE_AGENT`.
- RPM databases inside container images (`rpmdb.sqlite`).
- `UPGRADE_AGENT`, `ROTATE_KEY`, `ROTATE_CONSOLE_KEY` (post-MVP).
- Modes `embedded` and `ecs`.
- PHP-FPM pools as the runtime of a path application (today: the default `php` of the host).
