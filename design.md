# DepRadar Console — Design guidelines

> UI charter for the console. Source of truth for layout, tokens and components.
> Decisions behind it: `docs/cadrage.md` §3 ("Design de la console") and §9.

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
- **Tabs** under the header for the object's sub-views.
- **Two columns** on wide screens: main content + narrow side panel of key facts.
- **Dialogs** for creation forms (two-column fields when it helps), footer with Cancel + primary action.
- **Empty states**: one sentence + primary action ("No project yet." / "Add project").

## 6. Authentication screens

Centered, narrow card on a plain background; top bar with logo and theme toggle only.

1. **Sign in**: title, one-line hint, then **email + password form first** with a full-width primary button; below, an "or" separator and a secondary button **"Sign in with a passkey"**. No "Register" link (accounts are created by invitation), no third-party login.
2. **Second factor** (after password): TOTP code input (OTP component) if TOTP is configured, otherwise "We sent a code to j***@example.com" + code input + "Resend code" (rate-limited). Link to use a passkey instead when the user has one.
3. **Account security** (profile): list of passkeys (name, created, last used, revoke), add passkey, TOTP setup / reset.

## 7. Component map (shadcn kit)

| Need | Recipe |
|---|---|
| Buttons, icon buttons | `button`, `button-group` |
| Metadata grid, panels | `card`, `separator` |
| Forms | `field`, `input`, `label`, `native-select` / `select`, `checkbox`, `switch`, `textarea`, `input-otp` |
| Status / severity | `badge` |
| Navigation | `sidebar`, `breadcrumb`, `tabs`, `command` (palette) |
| Menus and overlays | `dropdown-menu`, `dialog`, `alert-dialog`, `sheet`, `tooltip`, `popover` |
| Lists | `table`, `pagination`, `empty`, `skeleton` |
| Feedback | `alert`, `toast` / `sonner`, `spinner` |
| Auth blocks | `login` block (adapted to section 6) |
