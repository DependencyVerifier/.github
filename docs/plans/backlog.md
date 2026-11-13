# Backlog

Work set aside, to pick up later. Each item points to its decisions in `cadrage.md` when there are some.

## Console

- **Step 1b: passkeys** (WebAuthn, optional, MVP §10.1). Library to choose (cadrage §12: Symfony support if any,
  else `web-auth/webauthn-framework`); a passkey as a sign-in method and as a second factor, enrolled from Account
  security, revocable; audited like the other factors.
- Offline mode (§11).
- Red Hat products not followed yet: EUS long life, ELS (RHEL 7), NVIDIA, AI; SUSE HPC, Manager, Leap Micro.
- Charts redrawn on a theme switch without reload.
- Notifications: Slack, Teams and Discord channels; role raised when a promoted recipient accepts a team invitation;
  recipients out of `maxMembers`; a stored notification-only flag.

## Agent

- Modes `embedded` and `ecs`.
