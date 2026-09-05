# Metrik — Innovation Presentation

An 8-slide, 16:9 slide deck for the Metrik hackathon submission, built as a
self-contained HTML/CSS/JS project (no build step, no framework, no CDN
dependency for the core mechanics — only Google Fonts loads externally).

## Structure

```
presentation/
├── index.html              All 8 slides (markup + content)
├── css/style.css           Design system, layout, print/PDF rules
├── js/presentation.js      Navigation, viewport scaling, keyboard/touch input
├── Metrik_Presentation.pdf Pre-exported PDF (8 pages, 16:9)
└── README.md
```

## Opening the presentation

Double-click `index.html`, or open it in any modern browser
(Chrome, Edge, Firefox). No server or install required.

## Navigating

| Action | Input |
|---|---|
| Next slide | → / ↓ / PageDown / Space, or the **›** button |
| Previous slide | ← / ↑ / PageUp / Backspace, or the **‹** button |
| Jump to a slide | Click a dot in the bottom bar |
| First / last slide | Home / End |
| Jump on load | Open `index.html#3` to land directly on slide 3 |
| Touch | Swipe left/right (phones, trackpads, touchscreens) |

The deck is designed at **1920×1080** and scales down (via a CSS `transform`)
to fit whatever window or screen it's opened on, so it looks correct on a
laptop, an external monitor, or a projector without any manual adjustment.

## Exporting to PDF

A pre-built `Metrik_Presentation.pdf` is already included. To regenerate it
after editing content:

1. Open `index.html` in **Chrome** or **Edge**.
2. Print (Ctrl/Cmd+P).
3. Set **Destination** → Save as PDF, **Layout** → Landscape,
   **Margins** → None, and enable **Background graphics**.
4. Save.

The stylesheet already declares `@page { size: 1920px 1080px; margin: 0; }`
and forces exact background/color reproduction in print, so each of the 8
slides becomes exactly one full-bleed PDF page at the correct 16:9 ratio —
nothing further needs to be configured in the print dialog beyond the
"Background graphics" checkbox (some browsers default this off).

The same result can be produced from a terminal with headless Chrome:

```
chrome --headless --disable-gpu --print-to-pdf=Metrik_Presentation.pdf \
  --print-to-pdf-no-header index.html
```

## What's on each slide

1. **Project & Team** — value proposition, key numbers, team block
   (team name / college / mentor are placeholders — see below)
2. **Problem** — current situation → problem → consequence → need
3. **Solution** — the actual input→processing→intelligence→output→action
   pipeline, as implemented
4. **AI Component** — the two XGBoost models, feature pipeline, tech stack
5. **Prototype** — a browser-frame mockup of the real dashboard, rebuilt
   from the project's own React components and demo data
6. **Innovation** — traditional → gap → innovation → advantage, plus the
   four differentiators
7. **Impact** — 5 impact cards, each explicitly labeled Demonstrated /
   Expected / Potential
8. **Roadmap** — current prototype → validation → integration →
   deployment → scale

Every metric, model name, and architectural detail is pulled directly from
the project's source and model metadata (`backend/models/*_meta.json`,
`backend/utils/tool_physics.py`, `README.md`) — nothing is invented.

## Before presenting: fill in the team block

Slide 1 has four placeholder fields — **Team Name**, **College /
Organization**, additional **Team Members**, and **Faculty Mentor** — none
of which exist anywhere in the project repository, so they were left as
bracketed placeholders rather than guessed. Edit them directly in
`index.html` under `<section id="slide-1">` → `.s1-team`.

## Editing content

All slide content lives in `index.html`; all visual styling lives in
`css/style.css` (organized in one section per slide, matching the HTML
comments). There is no build step — edit and reload.
