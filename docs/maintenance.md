# Repository maintenance

Maintainer: [Eduardo Bittencourt](https://github.com/eduardobittencourt).
This guide describes the intended contribution policy. Configuration files alone
are not evidence that a hosted service or protection is active.

Verified on 2026-11-03 UTC: vulnerability alerts, Dependabot security updates and
private vulnerability reporting are enabled. Preexisting secret scanning and push
protection remain enabled. Squash is the only enabled merge method, and merged
topic branches are deleted automatically. The `Protect release tags` ruleset is active for `v*`, restricting updates and
deletions with no bypass and no restriction on new tag creation. Main-branch
protection and new analysis/review checks still await live validation; the merge
policy below is the intended policy.

## Merge policy

Changes to `main` go through a pull request with one eligible approval, resolved
conversations and successful universal checks. New commits dismiss earlier
approvals. The author cannot approve their own PR. Code owners guide review;
a separate code-owner approval is not required. There is no routine maintainer
or bot bypass. Use squash merges and delete merged topic branches.

A CodeRabbit completed check or COMMENTED review is not an approval. Count only
an eligible GitHub APPROVED review; otherwise obtain approval from another
eligible human reviewer. Never reduce the approval count to unblock a sole
maintainer.

Observe check names and application IDs on internal, fork and Dependabot PRs
before adding required checks. Python tests, lint and package acceptance must
work without repository secrets. Sonar is a review requirement where analysis
runs, but must remain outside global required checks until a supported safe path
is demonstrated for every origin. Record its absence on fork/Dependabot PRs;
main analysis provides follow-up and does not retroactively protect their merge.
Sonar CI skips fork PRs and Dependabot because they cannot use repository secrets.
Apply the same availability rule to CodeRabbit checks.

Protect `v*` tags against update and deletion while allowing authorized creation.
Do not publish a release to test protection. Follow [release gates](releases.md).

## Inspect effective settings

Run with an authenticated GitHub CLI as a repository administrator:

```sh
gh api repos/eduardobittencourt/kobra-lan-cli
gh api repos/eduardobittencourt/kobra-lan-cli/rulesets
gh api repos/eduardobittencourt/kobra-lan-cli/branches/main/protection
gh api repos/eduardobittencourt/kobra-lan-cli/vulnerability-alerts
gh api repos/eduardobittencourt/kobra-lan-cli/automated-security-fixes
gh api repos/eduardobittencourt/kobra-lan-cli/private-vulnerability-reporting
gh pr checks PR_NUMBER
gh api repos/eduardobittencourt/kobra-lan-cli/pulls/PR_NUMBER/reviews
```

The vulnerability-alerts endpoint returns 204 when enabled and 404 when disabled
(or inaccessible). Rulesets and classic branch protection are separate; a 404
on the latter does not prove rulesets are absent. Preserve existing secret
scanning and push protection when changing other security settings.

## Analysis and dependency maintenance

Keep GitHub Actions pinned to full commit IDs with version comments. Review
Dependabot Python (`uv` ecosystem, including `uv.lock`) and Actions updates weekly; group compatible minor/patch
updates and review majors separately. Verify `uv.lock` and regenerate the runtime
export when needed, even if Dependabot does not update the derived file:

```sh
uv lock
uv export --locked --no-dev --no-emit-project --no-header --no-annotate \
  --format requirements-txt > requirements-runtime.txt
uv sync --locked
```

Run the checks in CONTRIBUTING.md and the archive/installation gates in
[releases.md](releases.md) when packaging inputs change. Development tools must
not appear in exported runtime requirements.

Sonar project: `eduardobittencourt_kobra-lan-cli`, organization
`eduardobittencourt`. Preserve the existing Quality Gate and review findings
against [the security decisions](pairing-security-review.md). Do not exclude
production code, lower the gate, or accept findings merely to pass CI. Import
coverage from the offline unit run and derive the version from
`scripts/release_version.py`. Record the automatic-analysis setting, then disable it immediately before the
first CI scanner run: Sonar rejects CI analysis while automatic analysis is on.
Confirm successful analysis and coverage import; restore automatic analysis if
either fails. Store scanner tokens in repository secrets, never in files or logs. Do
not execute contributed code or artifacts in privileged events such as
`pull_request_target` to obtain secrets for forks.

## Change records and recovery

Before changing hosted settings, keep a private, sanitized record of the exact
fields/rules being changed and their previous values. Record verification time,
source commit, check names/apps, approval eligibility, analysis mode, imported
coverage and concrete service limitations. Do not publish credentials or private
installation context in this repository.

Restore only settings modified by the change: update/delete only its ruleset IDs,
restore the previous merge/security flags and previous Sonar automatic-analysis
value. Preserve preexisting scanning, push protection and unrelated rules. Revert
versioned configuration with a reviewed PR. Do not delete/recreate existing tags,
replay publication, change printer state, or restore secrets from public files.
