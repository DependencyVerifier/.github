# Console step 1 — status

Where the work on [step 1 of the console](console-step-1.md) stands (Identity, Organization, Audit), and what comes next. Updated on 2026-11-10.

## Resume on another machine

```bash
git clone git@github.com:DependencyVerifier/.github.git ~/Workspace/DepVerifier/.github
~/Workspace/DepVerifier/.github/scripts/workspace.sh
```

`workspace.sh` clones the four repositories over SSH, runs `make start` in `console/`, creates the dev super admin `admin@depverify.localhost` (password in `console/var/dev-super-admin.txt`, mode 600), builds the agent and the agent image. Then open https://console.depverify.localhost (mails in Mailpit, http://localhost:8025).

Working agreement:
- The developer runs the tests and Infection (`make test`, `make qa`, `make infection`); the assistant gives the command and reads the output.
- `make qa` is green (100 % MSI) before every console commit.
- Commits: subject line only, never committed without being asked.

## Delivered (all pushed to `main`)

| Commit | Content |
|---|---|
| `console` `05ed8fe` | Commit 1 of the plan: shared kernel, CQRS buses, append-only audit log |
| `console` `6cb2211` | Commit 2: authentication, second factor, account security |
| `console` `e502b05` `486ef81` `4d90709` `f7bd6ec` | Reset link session, Lucide icons, stylesheet as a link tag, sidebar logo |
| `console` `07a1a23` | Commit 3: teams, projects, memberships, permissions, quotas (DataTable listings) |
| `console` `ef9490f` | Rank check before changing an extra permission (security review) |
| `console` `b6b1e05` | Generic `FormDialog` modal; team creation in a dialog |
| `console` `088edb6` | Teams entry highlighted, super-admin navigation grouped |
| `console` `5055aaa` | Team edit dialog (name + quotas, the quotas page is gone); user creation by email invitation |
| `console` `d4df15c` | Soft delete of users (Deleted state, "Show deleted", Restore as deactivated); team page and list fixes |
| `console` `2afafdb` | User edit dialog: display name, super admin moved into the dialog |
| `console` `2827c39` | Email change confirmed by a link sent to the new address (CI not checked yet) |
| `console` `0c3a914` | Email change: own re-authenticated dialog, refused on a super admin, reset and setup links to the previous address closed at confirmation |
| `console` `fe74b1f` | Team creation: first admin picked with an account autocomplete (`symfony/ux-autocomplete`) and admitted at once; unknown email invited by Identity in the same transaction (`AccountProvisioning` port) |
| `console` `ccaf575` `d0e5f1b` | Account picker shown as a single input above its dialog; cascade deletion of a team from `/admin/teams` (decision 16) |
| `console` `a8fefa6` | Team page in 4 tabs with their own URL (Overview, Projects, Members, Settings), creation forms in guarded dialogs, styled quota gauges |
| `console` `abcf7ad` `bfa24bf` `1d58c2e` | Log out from the menu item itself; extra permissions dialog (atomic change); team sections in the sidebar, current team marked |
| `console` `07dc1fb` | Project page in sections, calmer DataTables (card, always-on search), ⋯ row menus, sidebar team / project groups, creation buttons disabled by quota (Turbo refresh), Enter submits dialogs |
| `console` `0f56418` | Members + pending invitations everywhere (project, `/admin/users`), member search by email (`MatchAccounts`), Re-sync memberships, audit pages (`/admin/audit`, `/teams/{id}/audit`; non-UTF-8 cursor answered 422), rank rules (TEAM_MEMBER as PROJECT_MEMBER, team members removed from a project by a TEAM_ADMIN only), team lock test with two PostgreSQL sessions, Compose project `depverifier-console` |
| `.github` `d84291d` | Step 1 decisions recorded in `cadrage.md` and `design.md` |
| `.github` `a2aa389` | `scripts/workspace.sh` |

## Decisions taken after the plan

Decided with the developer during the implementation; not all of them are in `cadrage.md` yet (see the backlog).

- **Listings are DataTables** (`omines/datatables-bundle`, data through the query bus) instead of lazy frames; frames stay for the quota gauges and the audit log.
- **Creation and edit forms open in a modal**: `<twig:FormDialog>` loads its form from a GET|POST endpoint through `Shared\UI\Action\DialogForm` (see the console `CLAUDE.md`).
- **Team edit** (super admin): name and the 9 quotas in one dialog (`UpdateTeam`); the `TEAM_ADMIN` still renames through `RenameTeam`.
- **User creation** (`/admin/users`): an email only; the account has no password, a single-use setup link (7 days) lets its holder choose one, then the second factor works as usual. "Forgotten password" also works for an invited account.
- **User deletion**: soft delete, two distinct states. `Deleted` = deactivated and hidden from the list, `Restore` brings it back as deactivated (reactivation stays explicit). Never oneself, never the last super admin.
- **User edit**: display name (100 characters, shown in the list and the sidebar), instance role only (super admin buttons, re-authenticated). The email has its own "Change email" dialog (`/admin/users/{userId}/email`, re-authenticated, refused on a super admin: revoke the role first), applied only once confirmed from a 24-hour link sent to the new address; every session revoked, alert to the previous address, open reset and setup links closed.
- **Team creation with an autocomplete on the instance accounts** (done, `fe74b1f`; decision 12 of `cadrage.md`): an existing account becomes `TEAM_ADMIN` directly (alert email, no invitation to accept); an unknown email creates the account by invitation (7-day setup link) and makes it `TEAM_ADMIN` directly.
- **Team page in 4 tabs** (done), each its own URL, redesigned with the `impeccable` skill: Overview (readable quota gauges, alerts, shortcuts), Projects, Members (members + pending invitations), Settings (name). Creation forms in modals.

## Next task: none planned in step 1

Step 1 (Identity, Organization, Audit) is complete. Next: step 2, Fleet (hosts, agents, enrollment, signed agent API, orders).

## Backlog

Concurrency: the quota and the last team admin rely on the team row lock taken first by every command (`TeamLockTest`, two real sessions) and on the order "lock, then count" of each handler (`LocksAndRanksTest`). A test dispatching two real commands in parallel was ruled out: its audit entries would be committed in the append-only log of the test database and break the counts of other tests.

In this order, unless decided otherwise:

1. Check the CSP / DataTables / Turbo behaviours in a real browser on a fresh profile (largely done through Playwright during the UI work; the Vite HMR websocket is blocked by the CSP when the dev ports are remapped).
2. Clean up the old Compose volumes `console_*` once the `depverifier-console_*` copies are confirmed (`docker volume rm console_database_data console_caddy_data console_caddy_config`).

Decided on 2026-11-11 (recorded in `cadrage.md` and `design.md`): a `TEAM_MEMBER` ranks as a `PROJECT_MEMBER` in its team's projects; a `PROJECT_ADMIN` never removes a member of the team from a project; the Compose project name is pinned (`depverifier-console`).
