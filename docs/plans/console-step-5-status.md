# Console step 5 — status

Where the work on [step 5 of the console](console-step-5.md) stands (dashboards by team, project, environment and host, filtered list of findings), and what comes next. Updated on 2026-11-12.

Resume on another machine and working agreement: see [step 1 status](console-step-1-status.md). After `yarn install` (Chart.js came with `symfony/ux-chartjs`), reload the Vite dev server if the charts do not show.

## Delivered (committed on `main`, not pushed yet)

| Commit | Content |
|---|---|
| `console` (step 5) | `symfony/ux-chartjs` and `chart_theme_controller.ts`; placement of the findings (subject name, environment, project) and `ApplicationPlacementChanged`; suggested upgrade of an end of life; `GetExposureSummary` and `ListTeamFindings`; Findings sections of the team and of the project, environment page, summary frames (team and project overviews, host page) |
| `console` + `.github` | Decisions 54–57 in `cadrage.md`, `design.md`, this plan and status, console `CLAUDE.md` |

## Decisions taken after the plan

- The ends of life of a list are ordered by date (the nearest, or already past, first) after the vulnerabilities.
- The project filter of the team list offers the projects with an environment (only they hold applications).
- The existing findings get their placement at the next computation (`make findings-refresh`).

## Next task: browser check, then step 6

1. In a real browser: the Findings section of the team (charts in light and dark themes, filters), a project's section, an environment page, the frames of the overviews and of a host page.
2. Step 6: notifications (channels, rules per project, digests, silent agent, expiring acceptances), on the events Exposure already publishes (`FindingOpened`, `FindingFixed`, `RiskAccepted`, `RiskAcceptanceRevoked`).

## Backlog

- Component matrix of an environment (which version runs on which host, cadrage §5bis).
- Charts redrawn on a theme switch without reload.
