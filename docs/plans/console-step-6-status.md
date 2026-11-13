# Console step 6 — status

Where the work on [step 6 of the console](console-step-6.md) stands (notifications by email and signed webhook, rules
per project and per fleet, digests, notification-only recipients), and what comes next. Updated on 2026-11-13.

Resume on another machine and working agreement: see [step 1 status](console-step-1-status.md). After pulling, run
`make db-migrate` and `docker compose up -d worker` (the worker now consumes `notifications` too).

## Delivered (committed on `main`, not pushed yet)

| Commit | Content |
|---|---|
| `console` `f27e33e` | Contracts and events, outbox, sending of the emails and signed webhooks, `notifications-check` and `notifications-digest` |
| `console` `4d6650c`, `a7dbd32`, `8d3070c` | Notification-only recipients: invited by address, attached once confirmed; promotion by invitation or as first team admin |
| `console` `63bfbb1`, `bf107cf` | Commands of the webhooks, rules and subscriptions; Notifications section of the team and tab of the project |
| `console` + `.github` | Decisions 58–66 in `cadrage.md`, `webhook.md`, `design.md`, this plan and status, console `CLAUDE.md` |

## Cron (production)

```
*/5 * * * *  make notifications-check
0 7 * * *    make notifications-digest
```

## Next task: browser check

1. Team: create a webhook (secret shown once), send a test to a local receiver (`NOTIFICATION_WEBHOOK_ALLOW_PRIVATE=1`
   in `.env.local`), a fleet rule, my fleet subscription.
2. Project: a rule, add a recipient, confirm it from Mailpit, then `make fleet-fake-agent a=inventory` and check the
   email and the signed request.

## Known limits

- A promoted notification-only account stays `TEAM_GUEST` when it accepts a team invitation (the acceptance does not
  raise an existing role).
- Recipients are team members: they count in `maxMembers` too.
- The promotion relies on the lack of `account.login`; a stored "notification-only" flag will be needed if a login
  revocation is ever added.
