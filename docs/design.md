# DependencyVerifier Console — Design guidelines

> UI charter for the console. Source of truth for layout, tokens and components.
> Decisions behind it: `docs/cadrage.md` §3 ("Design de la console") and §9.
> **Full design system** (brand book, every token per theme, 20 components with live previews and usage rules, fonts, icons, signature): https://claude.ai/artifact/5kntDaEcezCeUewSM4cUjj. It was built from this repository; keep its `tokens.json` and `console/assets/styles/app.css` in sync when a value changes.
> **Logo and social images**: `docs/brand/` (mark SVGs, `favicon.svg`, `logo-sheet.png`) and `docs/brand/social/` (og:image 1200×630 and GitHub social preview 1280×640 for the console, the agent and the agent image). Source canvas: https://claude.ai/artifact/Wzhm6p5WQpLSJQwznKgeS5. The console serves `public/favicon.svg` and `public/og-image.png` (copies).

## 1. Principles

- **Quiet and dense.** An operations tool: lots of facts per screen, little decoration. Neutral greys, generous whitespace between groups, tight spacing inside a group.
- **One accent color.** Neutral palette plus a single accent for primary actions and focus. Color otherwise carries **meaning only** (status, severity).
- **Status by small colored dots and badges**, never by large colored areas. Severity: critical / high / medium / low / none, plus KEV and EOL markers.
- **Technical values in monospace**: IP addresses, versions, purls, digests (`sha256:…`), key fingerprints, UUIDs, hostnames, paths.
- **Light, dark and system themes.** System is the default; the user can switch (toggle in the top bar / account menu). Both themes are first-class.
- **No external resources.** Fonts, icons and scripts are self-hosted (sovereignty, cadrage §7). No Google Fonts, no CDN.
- **Inspiration, not imitation.** Reference screenshots of a third-party product guided the style. We reuse the *style* (shadcn-like layout and density), never another product's name, logo, wording or assets.

## 2. Stack

- **Tailwind CSS v4**, built by **Vite** through **Symfony Reprise** (`@tailwindcss/vite`).
- **Symfony UX Toolkit, `shadcn` kit**: components installed with `bin/console ux:install <recipe> --kit=shadcn` and copied into `templates/components/` and `assets/controllers/`. They are **our code**: adapt them freely; re-running `ux:install` shows a diff against the kit.
- **Twig Components** for every reusable piece; **Live Components** for interactive parts (filters, live status); **Turbo** for navigation and frames.
- Icons: a self-hosted icon set (e.g. Lucide via Symfony UX Icons with local caching), stroke style, 16–20 px.

## 3. Tokens

Defined as CSS variables in `assets/styles/app.css` (shadcn kit block), mapped to Tailwind with `@theme inline`. Dark values under `.dark` (class on `<html>`, set from the theme preference; `prefers-color-scheme` when "system").

| Token | Use |
|---|---|
| `--background` / `--foreground` | Page background and main text |
| `--card` / `--card-foreground` | Cards, metadata grid, dialogs |
| `--muted` / `--muted-foreground` | Labels, secondary text, subtle backgrounds |
| `--border` / `--input` / `--ring` | Borders, inputs, focus ring |
| `--primary` / `--primary-foreground` | Primary buttons (near-black in light, near-white in dark) |
| `--accent` | Hover / selected nav item |
| `--destructive` | Delete, revoke, errors |
| `--sidebar-*` | Sidebar background, text, active item |
| Status: `--status-ok`, `--status-warning`, `--status-critical`, `--status-unknown` | Health dots, agent status |
| Severity: `--sev-critical`, `--sev-high`, `--sev-medium`, `--sev-low` | Finding badges |

Radius: medium (`--radius` ≈ 0.5rem). Shadows: almost none; separation by borders.

## 4. Typography

- **Sans** for UI, **mono** for technical values. Self-hosted variable fonts (candidates: IBM Plex Sans / IBM Plex Mono, or Inter / JetBrains Mono), `font-display: swap`.
- Scale: page title ~1.5rem semibold; section title ~1rem semibold; body 0.875rem; labels 0.75–0.8125rem muted.
- Numbers in tables use tabular figures.

## 5. Layout

```
┌────────────┬─────────────────────────────────────────────────────┐
│ [Team ▾]   │ Breadcrumb: Projects / my-project / prod            │
│ Search ⌘K  │ ┌──┐ Title                              [☆] [⋯] [Primary]│
│            │ └──┘ Subtitle (type · parent)                        │
│ Overview   │ ┌──────────┬──────────┬──────────┬──────────┐        │
│ Projects   │ │ Label    │ Label    │ Label    │ Label    │ ← metadata grid
│ Hosts      │ │ value    │ value    │ value    │ value    │        │
│ Findings   │ └──────────┴──────────┴──────────┴──────────┘        │
│ Agents     │ Overview  Findings  Components  Hosts   ← tabs       │
│ ...        │ ┌───────────────────────────────┐ ┌─────────────┐    │
│            │ │ Main content (sections)       │ │ Side panel  │    │
│ Help       │ │                               │ │ (key facts) │    │
│ Account    │ └───────────────────────────────┘ └─────────────┘    │
└────────────┴─────────────────────────────────────────────────────┘
```

- **Sidebar** (left, fixed): team switcher at the top (team name + plan/role), search (⌘K / Ctrl K command palette), main navigation, then help and the account block at the bottom. Collapsible on small screens (sheet).
- **Breadcrumb** above every object page.
- **Object header**: square icon, title, subtitle ("Server in production", "PostgreSQL in project / env"), favorite star, `⋯` menu (dropdown: secondary and destructive actions), one primary button at most.
- **Metadata grid**: bordered card split into cells, each with a muted label and a value (mono when technical), optional copy / edit icon buttons.
- **Tabs** under the header for the object's sub-views: **one URL per tab** (links, `<twig:TabNav>`, `aria-current="page"`, the look of the kit's `line` tabs), never content hidden client-side. A tab the actor may not open is not shown and its URL answers 403. The header's single primary action belongs to the current tab (team page: "New project" on Projects, "Invite member" on Members).
- **Two columns** on wide screens: main content + narrow side panel of key facts.
- **Dialogs** for creation forms (two-column fields when it helps), footer with Cancel + primary action. A dialog endpoint serves its form only to whom may submit it (404 out of scope, 403 without the permission). A destructive confirmation (delete a team) is a plain kit `Dialog` holding the field-less form.
- **Empty states**: one sentence + primary action ("No project yet." / "Add project").
- **Listings are DataTables** (server-side: paging, sort, search through the page URL), in a bordered card; actions of a row are small buttons or an inline role select in the last column. No client-side table of more than one page.
- **Lazy zones** (quota gauges, audit log): a Turbo Frame rendered first as `skeleton` lines close to the final size, then filled; on failure an inline alert "Couldn't load this section" with **Retry**. Never a spinner over the whole page.
- **After an action**: the form stays in place; a validation error re-renders it (422) with its values (never a password or a code); a success answers a Turbo Stream that refreshes the lists and gauges concerned and appends an `alert` at the top of the page, with no reload. Refusals (quota, last admin, permission) use the same alert, in destructive style.
- **Quota gauges**: one row per quota, label then "3 of 5" in tabular figures, then a native `<meter class="quota-meter">` drawn as a thin bar by `assets/styles/meter.css` (`data-state` ok / warning / reached → `--status-ok` / `--status-warning` / `--destructive`; no inline style under the CSP). Banners above them: warning from 80 %, destructive at 100 % ("the limit of N is reached, contact the instance administrator"). Quotas whose feature is not there yet are folded under a `<details>`, limits only.
- **Sidebar logo**: the application logo at the top of the sidebar, above the team switcher; the switcher lists the user's teams with their role.
- **Footer** (`AppFooter`, every layout): copyright on the left, "Made by" + the Romain MILLAN tag on the right (Romain-MILLAN-Tag git submodule, muted color in both themes).

## 6. Authentication screens

Centered, narrow card on a plain background; top bar with logo and theme toggle only.

1. **Sign in**: title, one-line hint, then **email + password form first** with a full-width primary button; below, an "or" separator and a secondary button **"Sign in with a passkey"**. No "Register" link (accounts are created by invitation), no third-party login.
2. **Second factor** (after password, every sign-in): one `one-time-code` input (not the segmented OTP component: backup codes are alphanumeric), TOTP if configured, otherwise "We sent a code to j***@example.com" + "Resend code" (rate-limited). Checkbox **"Trust this device for 30 days"**, link "Use a backup code". Link to use a passkey instead when the user has one (step 1b).
3. **Account security** (profile): password change, TOTP setup (QR code generated locally + secret in text, then confirmation code), backup codes shown **once** (page not cached, no redirect), regeneration; a "TOTP recommended" banner for a super admin without TOTP. Passkeys list in step 1b. Sensitive actions go through **Re-authenticate** (password then second factor) after 10 min.
4. **Password forgotten / reset**: the same answer whether the account exists or not; the emailed link opens a small relay page ("Continue") before the new password form, so the token never stays in the address bar.
5. **Invitation**: relay page from the email, then one page with the same text in every case: "Accept" when signed in with the invited email, "Sign in" when the account exists, otherwise "Choose a password" (the sign-in and second factor follow, then the page comes back).
6. **Link expired**: one neutral page (410) for an expired, used or revoked link.

## 7. Component map (shadcn kit)

| Need | Recipe |
|---|---|
| Buttons, icon buttons | `button`, `button-group` |
| Metadata grid, panels | `card`, `separator` |
| Forms | `field`, `input`, `label`, `native-select` / `select`, `checkbox`, `switch`, `textarea`, `input-otp` |
| Status / severity | `badge` |
| Navigation | `sidebar`, `breadcrumb`, `tabs`, `command` (palette) |
| Menus and overlays | `dropdown-menu`, `dialog`, `alert-dialog`, `sheet`, `tooltip`, `popover` |
| Lists | DataTables (`<twig:DataTable>`, `assets/styles/datatables.css`), `empty`, `skeleton` |
| Feedback | `alert`, `toast` / `sonner`, `spinner` |
| Auth blocks | `login` block (adapted to section 6) |
