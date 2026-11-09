# Governance

Who can change what in the DependencyVerifier organization.

## Policy

- **Only organization owners push to `main`** (today: Romain Millan). Everyone else proposes changes through a pull request from a fork; an owner reviews and merges it.
- `main` can't be deleted or force-pushed, by anyone but an owner.
- Workflows triggered by a pull request from a fork wait for an owner's approval.
- Members get read access by default and can't create or fork repositories; write access is granted per repository when needed.

## How it is enforced

| Setting | Where | State |
|---|---|---|
| Members' default permission `read`, no repository creation, no fork of private repositories | Organization settings | **Applied** (08/11/2026) |
| Ruleset "Protect main" ([`rulesets/protect-main.json`](rulesets/protect-main.json)): restrict updates, require a pull request, block deletion and force push, bypass for organization admins only | Each repository | **Pending**: GitHub Free refuses rulesets on private repositories |
| Approval of fork workflows for all outside contributors | Each repository (Actions) | **Pending**, same script |

While the repositories are private, the policy already holds: an owner is the only one with write access, and nobody outside the organization can see the repositories, so no pull request can come from outside.

## When the repositories go public

```bash
gh repo edit DependencyVerifier/console --visibility public --accept-visibility-change-consequences
./governance/apply-rulesets.sh
```

The script is idempotent: it creates the ruleset, or updates it when it already exists, on every public repository, and skips the private ones. Check the result under each repository's Settings › Rules › Rulesets. A new repository needs the same command.

Alternative without going public: the GitHub Team plan allows rulesets on private repositories (and organization-wide rulesets).
