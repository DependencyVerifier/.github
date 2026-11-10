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
- **Team page in 4 tabs** (not done yet), each its own URL, redesigned with the `impeccable` skill: Overview (readable quota gauges, alerts, shortcuts), Projects, Members (members + pending invitations), Settings (name). Creation forms in modals.

## Next task: team page in 4 tabs (`console`)

Item 1 of the backlog below, not started.

## Backlog

In this order, unless decided otherwise:

1. **Team page in 4 tabs** with `impeccable` (decision above). The current page stacks every list and its quota bars are raw `<meter>`s.
2. Remaining items of the plan:
   - UI to grant / revoke extra permissions (commands and tests exist, route `TEAM_MEMBER_EXTRA` has no controller);
   - "Re-sync memberships" button in `/admin/users`;
   - team audit page (`/teams/{teamId}/audit`) and global audit (`/admin/audit`);
   - concurrency tests (quota, last admin);
   - check the CSP / DataTables / Turbo behaviours in a real browser.
3. Record the decisions above in `docs/cadrage.md` (§3, §7, §7bis) and `docs/design.md` (§5, §6).
4. Open questions for the developer:
   - `RoleAuthority` only treats `TEAM_ADMIN` as covering project roles: should a `TEAM_MEMBER` count as `PROJECT_MEMBER` and a `TEAM_VIEWER` as `PROJECT_VIEWER` for the rank (today the ○ `project.members.manage` of a `TEAM_MEMBER` only works on projects where they also have a project role)?
   - Pin the Compose project name in `console/compose.yaml` (`name: depverifier-console`): every checkout named `console` shares the project `console`, so another checkout's containers can replace these ones (it happened once).
