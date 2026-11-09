#!/bin/sh
# Applies the branch protection of DependencyVerifier to every repository of the organization.
# Run it once the repositories are public (GitHub Free refuses rulesets on private repositories),
# from this folder, with an organization owner logged in: `gh auth login`.
#
#   ./apply-rulesets.sh            # all repositories
#   ./apply-rulesets.sh console    # one repository
set -eu

main() {
    org="DependencyVerifier"
    dir="$(cd "$(dirname "$0")" && pwd)"
    ruleset="$dir/rulesets/protect-main.json"
    name="Protect main"

    if [ "$#" -gt 0 ]; then
        repos="$*"
    else
        repos="console agent agent-image .github"
    fi

    for repo in $repos; do
        visibility="$(gh api "repos/$org/$repo" --jq .visibility)"
        if [ "$visibility" != "public" ]; then
            echo "skip $repo: $visibility (rulesets need a public repository on GitHub Free)" >&2
            continue
        fi

        # Create the ruleset, or update it in place when it already exists (idempotent).
        id="$(gh api "repos/$org/$repo/rulesets" --jq ".[] | select(.name == \"$name\") | .id")"
        if [ -n "$id" ]; then
            gh api -X PUT "repos/$org/$repo/rulesets/$id" --input "$ruleset" --silent
            echo "$repo: ruleset updated"
        else
            gh api -X POST "repos/$org/$repo/rulesets" --input "$ruleset" --silent
            echo "$repo: ruleset created"
        fi

        # Pull requests from forks: workflows need a maintainer's approval for every outside contributor.
        gh api -X PUT "repos/$org/$repo/actions/permissions/fork-pr-contributor-approval" \
            -f approval_policy=all_external_contributors --silent 2>/dev/null \
            || echo "$repo: could not set the fork workflow approval (Actions disabled?)" >&2
    done
}

main "$@"
