# Maintenance Portal UI Redesign

## Overview

將 maintenance_portal 的所有 Portal User 頁面重新設計，對齊 `woow_portal_ui` 的 `--wt-*` Design Token 體系和 `.wt-*` 元件 class。

**兩種行為：**
- 只裝 `maintenance_portal`：完整的 `.wt-*` 元件 + 紫色主題 + 原生 Odoo searchbar dropdown
- 加裝 `woow_portal_ui`：bridge 模組自動啟用 → 主色變藍 + 篩選變 pill segment + icon 對齊

## Architecture

```
maintenance_portal/                     ← 重寫
├── static/src/css/portal.css           ← 全面重寫
├── views/portal_templates.xml          ← 全面重寫 6 個模板

maintenance_portal_ui_bridge/           ← 新建
├── __manifest__.py                     ← auto_install: True
├── __init__.py
├── views/portal_templates.xml          ← XPath 覆寫篩選 → pill
├── static/src/css/bridge.css           ← token 覆寫 + pill 樣式
```

## Design Token

```css
:root {
    /* Primary（紫色系） */
    --wt-primary:     #714B67;
    --wt-primary-700: #5E3D56;
    --wt-primary-100: #f0e8ee;
    --wt-primary-50:  #f8f4f7;

    /* Neutral */
    --wt-canvas:      #FAFBFF;
    --wt-surface:     #FFFFFF;
    --wt-line:        #e3e6ee;
    --wt-line-soft:   #eef0f5;
    --wt-ink:         #1a1d29;
    --wt-ink-2:       #4a4e5b;
    --wt-ink-3:       #8b8e9a;
    --wt-ink-4:       #b6b9c4;

    /* Tone */
    --wt-tone-coral:  #f45d6d;
    --wt-tone-green:  #8CD37F;
    --wt-tone-yellow: #F8D158;
    --wt-tone-cyan:   #7BDBE0;
    --wt-tone-orange: #E66D3E;
    --wt-tone-lilac:  #C09FE0;

    /* Tint */
    --tint-green:     #ebf7e7;
    --tint-cyan:      #e3f8f9;
    --tint-yellow:    #fff5d4;
    --tint-coral:     #fde9eb;
    --tint-lilac:     #f1e8f8;

    /* Radius */
    --r-sm:   4px;
    --r-md:   8px;
    --r-lg:   12px;
    --r-pill: 999px;

    /* Shadow */
    --sh-1: 0 1px 2px rgba(20,22,30,.04), 0 2px 6px rgba(20,22,30,.04);
    --sh-2: 0 6px 16px rgba(20,22,30,.06), 0 2px 4px rgba(20,22,30,.04);

    /* Typography */
    --wt-font: "Outfit", "Noto Sans TC", -apple-system, sans-serif;
}
```

## Component Classes

### Card Grid
- `.wt-card-grid` — 3 col → 2 col → 1 col responsive grid

### Portal Card (List Page)
- `.wt-portal-card` — clickable card with hover effect
- `.wt-pc-head` / `.wt-pc-icon` / `.wt-pc-num` — card header
- `.wt-pc-meta` / `.wt-pc-row` / `.wt-pc-label` / `.wt-pc-value` — key-value pairs
- `.wt-pc-foot` — CTA footer

### Detail Card
- `.wt-detail-card` — white card with gradient header
- `.wt-detail-header` — gradient background (primary-50 → surface)
- `.wt-detail-body` / `.wt-detail-row` / `.wt-detail-label` / `.wt-detail-value`

### Progress Bar
- `.wt-progress` — flex container with connecting line
- `.wt-progress-step` — each node
- `.wt-step-circle` + `.is-done` / `.is-active` / `.is-pending`
- `.wt-step-label`

### Badge
- `.wt-badge` — base pill badge
- `.wt-badge-draft` — gray (ink-3)
- `.wt-badge-working` — cyan
- `.wt-badge-done` — green
- `.wt-badge-pending` — yellow
- `.wt-badge-category` — lilac

### Buttons
- `.wt-btn-ghost` — secondary/back button
- `.wt-btn-start` — Start Work (orange)
- `.wt-btn-done` — Mark as Done (green)

### Portal Home Card
- `.o_portal_index_card` — override Odoo native entry card

## Pages

### 1. Portal Home Card (`/my/home`)
- Use `portal.portal_docs_entry` with `.o_portal_index_card` styling
- Hover: translateY(-2px) + --sh-2 + border→primary

### 2. Maintenance Dashboard (`/my/maintenance`)
- Two `.o_portal_index_card` cards (Equipment + Requests)
- Same hover effect

### 3. Equipment List (`/my/equipments`)
- `.wt-card-grid` + `.wt-portal-card`
- Head: icon + equipment name + category badge
- Meta: serial number, location
- Foot: "View details →"
- Filter: keep native Odoo searchbar dropdown

### 4. Equipment Detail (`/my/equipments/<id>`)
- Two `.wt-detail-card` side by side (lg)
- Left: Equipment Information
- Right: Related Maintenance Requests (small `.wt-portal-card` cards)
- Bottom: Chatter

### 5. Request List (`/my/maintenance-requests`)
- `.wt-card-grid` + `.wt-portal-card`
- Head: icon + request name/number + stage badge
- Meta: equipment name, date
- Foot: "View details →"
- Remove dual layout (table + mobile cards) → unified card grid
- Filter: keep native Odoo searchbar dropdown

### 6. Request Detail (`/my/maintenance-requests/<id>`)
- Status Progress Bar (`.wt-progress`) at top
- Two `.wt-detail-card` side by side
- Left: Request Information
- Right: Update Status (buttons)
- Bottom: Chatter

## Bridge Module

### Trigger
`auto_install: True` when both `maintenance_portal` and `woow_portal_ui` are installed.

### What it does

1. **CSS Token Override** — `--wt-primary` → `--wt-blue` (portal_ui blue)
2. **Filter UI Override** — XPath replaces Odoo searchbar dropdown with pill segment
3. **Icon Alignment** — SVG icons → FontAwesome to match portal_ui style

### Behavior Matrix

| Aspect | maintenance_portal only | + woow_portal_ui (bridge) |
|--------|------------------------|---------------------------|
| Primary color | Purple #714B67 | Blue #6183fc |
| Home card icon | SVG | FontAwesome |
| List filter | Odoo dropdown | Pill segment |
| Card/Detail style | .wt-* (identical) | .wt-* (identical) |
| Badge colors | Tone colors (same) | Tone colors (same) |
