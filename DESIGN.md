# Design — Sloth Ledger

The written system behind the shipped build. If code and this file disagree, the
code is the bug; the recorded intent below is the source of truth.

## World

**The Card Tray.** A library date-stamp drawer for your minutes: manila index
cards on dark desk felt, verdicts as rubber stamps, a punched hole in every card
whose time came back, and a total that gets restamped when the ledger changes.

It refuses the category default: the KPI-tile grid, the hero-metric row, the
gradient SaaS shell, rounded-2xl cards on cream. A ledger should look like an
object you could drop on a desk.

## Colour

| Token | Hex | Role |
|---|---|---|
| `--felt` | `#14201b` | desk ground |
| `--felt-deep` | `#0d1613` | ground at the bottom of the page |
| `--card` | `#e7dcbe` | manila card stock |
| `--ink` | `#242019` | typed text, filled buttons, booked punches |
| `--ink-soft` | `#5b5344` | secondary text on card stock |
| `--rule` | `rgba(96,122,138,.28)` | ruled writing lines |
| `--violet` | `#4a3f7a` | **delegate** stamp (library stamp ink) |
| `--moss` | `#33573f` | **automate** stamp |
| `--seal` | `#a9341f` | booked stamp, errors |
| `--lamp` | `#e8c07a` | focus ring, links on felt |

Verdict colour is never the only signal: every stamp carries its word.

## Type

System faces only, because the page must render with the network off.

- Display and stamps: `"Franklin Gothic Medium", "Franklin Gothic", "Arial Narrow", "Segoe UI", sans-serif` — condensed grotesque, uppercase, tracking `.14em`–`.18em`.
- Typed card text and evidence: `"Cascadia Mono", Consolas, "Courier New", ui-monospace, monospace`.
- Body: `"Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif`.
- Card text sits on the ruled lines: `line-height: 28px` against a 28px rule pitch.

## Layout

- Page measure: `1120px`, gutters `24px` (`14px` under 520px).
- Top row: totals card (`0.86fr`) beside entry card (`1.14fr`); one column under 860px.
- Tray: `repeat(auto-fill, minmax(min(340px, 100%), 1fr))`, `18px` gap.
- Grid tracks are `minmax(0, 1fr)` everywhere. A grid track sized by min-content is how a card silently grows wider than a phone.
- Depth comes from one shadow with a real offset and blur; cards do not also carry a border.

## Components

- **Punch** — 13px felt-coloured circle with an inset shadow at the card's top-left. It is the receipt mark, not decoration.
- **Stamp** — 2px currentColor border, uppercase, rotated −2.4°, opacity .88 to read as ink.
- **Totals card** — no ruled lines (they would cut the display figure), double rule under the week line, stamped `15m`-scale figure with tabular numerals.
- **Entry card** — blank card with a dotted writing rule; one solid ink action, `STAMP IT`.
- **Chore card** — stamp and minutes on top, typed description, evidence line in mono behind a dashed rule, verdict reason, then either `RUN IT` (outline stamp) or `BOOKED` (sealed).
- **Tally** — fourteen punched circles, filled where minutes were booked, today outlined in seal red.

## Motion

Two physical gestures, no ambient animation: a card is dealt in
(`translateY(-14px) rotate(-1.5deg)` → settle, 340ms), and the total restamps
(scale 1.06 → 1, 420ms). `prefers-reduced-motion: reduce` removes both and
flattens the card rotations.

## Accessibility

- Body text ≥ 4.5:1 on both grounds; large figures ≥ 3:1.
- Focus ring: 3px `--lamp` with 3px offset on every interactive element.
- Minimum target 44px; the skip link is the first tab stop.
- The tally exposes a text alternative naming how many days booked time and the busiest day.
- Status changes announce through `aria-live="polite"` on the payoff line; errors through `role="alert"`.
- Keyboard operation is complete; `Run it` is a real button, not a clickable card.

## Raster provenance

Both shipping images were captured from the build in `main` with headless Edge,
so they show the app, not a mockup:

| File | Capture | Notes |
|---|---|---|
| `docs/desktop.png` | 1440×1500, `--headless=old`, DPR 1 | full first viewport plus the tray |
| `docs/mobile.png` | 496×2100 device pixels at `--force-device-scale-factor=1.2718` → 390 CSS px | Chromium enforces a ~496px minimum window; the scale factor buys a true 390px layout |

There are no stock images, no AI-generated imagery, and no icon fonts in the
product. The favicon is an inline SVG of a punched card.

## Known, accepted deviation

The mechanical detector flags the ruled lines as a `repeating-stripes-gradient`
advisory. It is the object's own material (a ruled index card), not a texture
applied to a generic surface, so it stays. All other detector warnings were
closed before shipping: label sizes, uppercase body labels, and tracking values.
