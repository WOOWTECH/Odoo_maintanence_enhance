# Woowtech Brand Portal Redesign — PRD

## Overview

CSS-only reskin of all 5 maintenance portal pages to align with Woowtech Smart Space Solution brand guidelines. No template structure changes. Two files modified: `portal_templates.xml` (minimal class additions) and `portal.css` (complete rewrite).

## Scope

- **Approach:** Full visual redesign (templates + CSS)
- **Fonts:** Font-agnostic — brand fonts declared in CSS with web-safe fallbacks
- **Pages affected:** Portal home cards, equipment list, equipment detail, request list, request detail
- **Files modified:** `static/src/css/portal.css`, `views/portal_templates.xml`
- **Risk:** Low-medium — visual changes only, no controller/model changes

---

## 1. Color System

### Primary Mapping

| Role | Old (Odoo Purple) | New (Woowtech) | HEX |
|------|-------------------|-----------------|-----|
| Primary / Interactive | `#714B67` | Primary Blue | `#6183FC` |
| Primary hover | `#5a3d53` | Darker Blue | `#4A6AD4` |
| Body text | `#495057` | Gray | `#646262` |
| Headings | `#212529` | Deep Gray | `#212121` |
| Backgrounds | `#f8f9fa` | Light Gray | `#EFF1F5` |
| Borders | `#e9ecef` | Warm border | `#E0E3EA` |

### Accent Color Assignments

| UI Element | Color | HEX |
|------------|-------|-----|
| Done/completed badges | Green | `#8CD37F` |
| In-progress badges | Yellow | `#F8D158` |
| New/active stage badges | Cyan | `#7BDBE0` |
| Category badges | Lavender | `#C09FE0` |
| Start work button | Orange | `#E66D3E` |
| Urgent/overdue (future) | Coral | `#F45D6D` |

### Color Ratio Target

- White `#FFFFFF` — 50% (page backgrounds, card backgrounds)
- Gray `#646262` — 20% (body text, labels, secondary UI)
- Deep Gray `#212121` — 10% (headings, emphasis text)
- Blue `#6183FC` — 10% (buttons, links, active progress, card accents)
- Accent colors — 5% (badges, status indicators, CTA buttons)
- Black — 5% (minimal, only in icon strokes)

---

## 2. Typography

```css
/* Title font stack */
font-family: 'Gira Sans', 'Inter', 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;

/* Body font stack */
font-family: 'Outfit', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;

/* Chinese font stack */
font-family: 'UD Digi Kyokasho', 'Noto Sans TC', 'Microsoft JhengHei', sans-serif;
```

- Titles: `font-weight: 600`
- Body: `font-weight: 400`
- Labels: `font-weight: 500`, Gray `#646262`
- Values: `font-weight: 400`, Deep Gray `#212121`

---

## 3. Component Design Specs

### 3.1 Equipment Cards (list page)

- White background, `border: 1px solid #E0E3EA`, `border-radius: 12px`
- Left accent: `border-left: 4px solid #6183FC`
- Card title: Deep Gray `#212121`, no link underline
- Whole card is clickable link
- Category badge: Lavender `#C09FE0`
- Location text: Gray `#646262`
- Remove card footer — whole card is the link
- Hover: `background: #EFF1F5` (no transform)
- Shadow: `0 1px 3px rgba(0,0,0,0.06)`

### 3.2 Request List Table (desktop)

- Header: `background: #EFF1F5`, text `#646262`, no border
- Row hover: `rgba(97, 131, 252, 0.04)`
- Stage badges: Cyan (new), Yellow (in progress), Green (done)
- Remove separate "操作" column — name is the link

### 3.3 Mobile Request Cards

- Same left-accent-border as equipment cards (`4px solid #6183FC`)
- Stage badge right-aligned with accent colors
- `border-radius: 10px`
- Hover: `background: #EFF1F5`

### 3.4 Progress Bar (request detail)

- Active circles: `#6183FC` (Primary Blue)
- Completed/done circles: `#8CD37F` (Green) with white check
- Connecting line active: `#6183FC`, inactive: `#E0E3EA`
- Current stage label: `#6183FC` bold

### 3.5 Info Cards (detail pages)

- Remove colored card-headers entirely
- White card, `border-radius: 12px`, `box-shadow: 0 1px 3px rgba(0,0,0,0.06)`
- Section title inside card-body: `#212121` text, `font-weight: 600`, preceded by a colored dot indicator:
  - Equipment info: Blue `#6183FC` dot
  - Related requests: Cyan `#7BDBE0` dot
  - Request info: Blue `#6183FC` dot
  - Update status: Green `#8CD37F` dot
- Label column: Gray `#646262`, `font-weight: 500`
- Value column: Deep Gray `#212121`

### 3.6 Buttons

- Primary (back to list): ghost style — `color: #646262`, `border: 1px solid #E0E3EA`, `border-radius: 8px`, `background: transparent`. Hover: `background: #EFF1F5`
- Start Work: `background: #E66D3E`, `color: white`, `border-radius: 8px`
- Mark Complete: `background: #8CD37F`, `color: white`, `border-radius: 8px`
- View detail links: `color: #6183FC`, hover: `#4A6AD4`

### 3.7 Badges

- `border-radius: 6px` (not pill)
- No border, `font-weight: 500`
- New/pending: `background: #7BDBE0`, `color: #212121`
- In progress: `background: #F8D158`, `color: #212121`
- Done: `background: #8CD37F`, `color: white`
- Category: `background: #C09FE0`, `color: white`
- Custom stage fallback: `background: #EFF1F5`, `color: #646262`

### 3.8 Empty States

- Centered layout, no alert box
- Large icon (48px) in `#E0E3EA`
- Text below in Gray `#646262`, `font-size: 0.95rem`
- Spacious vertical padding

### 3.9 Alerts

- No Bootstrap colored backgrounds
- Left border accent: `border-left: 4px solid [accent-color]`
- Background: `#EFF1F5`
- Success: Green `#8CD37F` left border + icon
- Info: Cyan `#7BDBE0` left border + icon

### 3.10 Chatter Section

- Full-width divider `1px solid #EFF1F5`, `margin-top: 3rem`
- Section title with Lavender `#C09FE0` dot indicator
- Widget internals: not restyled (Odoo built-in)

---

## 4. Global Micro Details

| Property | Value |
|----------|-------|
| Card border-radius | `12px` |
| Badge border-radius | `6px` |
| Button border-radius | `8px` |
| Card box-shadow | `0 1px 3px rgba(0,0,0,0.06)` |
| Card hover shadow | `0 2px 8px rgba(0,0,0,0.08)` |
| Link color | `#6183FC` |
| Link hover | `#4A6AD4` |
| Transition speed | `0.15s ease` |
| Border color | `#E0E3EA` |

---

## 5. Responsive Behavior

No structural changes to responsive layout — existing RWD (table/card dual layout, progress bar scroll, flex-wrap titles) is preserved. Only colors, fonts, spacing, and border-radius values change.

---

## 6. Implementation Plan

### Step 1: Rewrite `portal.css`
- Replace all color values
- Add font-family declarations
- Update border-radius, shadows, transitions
- Update responsive breakpoint styles with new values

### Step 2: Update `portal_templates.xml`
- Add section-title dot indicators (small `<span>` elements)
- Replace colored `card-header` with in-body section titles
- Make equipment cards full-click links
- Remove "操作" column from request table
- Update empty state markup (centered, no alert box)
- Update badge classes to use custom brand classes

### Step 3: Deploy & Verify
- Copy to container, upgrade module
- Screenshot all 5 pages at 3 viewports
- Run V1/V2/V3 test suites

### Step 4: Commit & Push
- Commit with descriptive message
- Push to main branch
