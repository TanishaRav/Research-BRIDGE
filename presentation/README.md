# Research Bridge — Interactive Pitch Deck

An interactive, 16:9 HTML slide deck for the **AWS Kiro Hackathon** at **Iowa State University** (November 17, 2026).

**Research Bridge — Bridging Research Interests, Discovery, Guidance & Engagement**

## Launch

Open `index.html` in a modern browser (Chrome or Edge recommended). No build step and no server are required — just double-click the file.

- An internet connection is used only to load the display/body fonts (Fraunces + Inter) from Google Fonts. Offline, the deck still works and falls back to Georgia / system sans-serif.
- Press **F** once the deck is open for true fullscreen presentation mode.

## Controls

| Key / action | Result |
|---|---|
| `→` · `Space` · `Enter` · `PageDown` · `›` | Next slide |
| `←` · `Backspace` · `PageUp` · `‹` | Previous slide |
| `F` · `⛶` | Toggle fullscreen |
| `Home` / `End` | First / last slide |
| `1`–`8` | Jump directly to a slide |
| Bottom dots | Click to jump to any slide |
| Swipe left / right | Navigate on touch screens |
| `?` | Keyboard help overlay |

Deep links work too: `index.html#3` (or `?s=3`) opens on slide 3 — handy for jumping back in after the demo.

## The eight slides

1. **Introducing Research Bridge** — title, team, champion, event.
2. **Opportunity vs. Access** — Iowa State R1 research ($462.35M, FY 2024), why undergraduate research matters, and the student–faculty disconnect.
3. **Meet Research Bridge** — the bridge reveal, the BRIDGE acronym, and Discover / Match / Grow.
4. **Key Features** — six capabilities of the platform.
5. **Live Demo: Meet Kiro** — the persona, the five-stage journey, and the handoff to the live app.
6. **Behind the Bridge** — built with AWS Kiro; the matching workflow and technical considerations.
7. **Built for Iowa State** — campus-wide impact network and the four-phase roadmap.
8. **The Next Connection** — before/after, the ask, and *Discover. Match. Grow.*

## The live demo (Slide 5)

The **LIVE DEMONSTRATION** button is a handoff cue. The deck does **not** embed a fake demo.

- Easiest option: start the real Research Bridge app yourself and switch to it with **Alt+Tab**, then switch back to this tab to continue.
- One-click option: open `index.html`, find the line near the bottom of the `<script>` that reads
  `const DEMO_URL="";` and set it to the running app's URL (for example `const DEMO_URL="http://localhost:3000";`).
  The button will then open the app in a new tab.

## Branding

- `logo.png` is the real Research Bridge logo and is used unmodified — top-left on every slide, and featured larger on slides 1, 3, and 8.
- Iowa State palette: Cardinal `#C8102E`, Gold `#F1BE48`, Warm Ivory `#F8F6F0`, White, Charcoal `#222222`.
- The full brand name appears in the footer of every slide, with a slide number opposite.

## Accuracy notes

- The `$462.35M` FY 2024 research-expenditure figure is attributed on-slide to Iowa State / the NSF HERD survey.
- AWS Kiro is the only development tool claimed. No other AWS services are implied.
- Future items (campus authentication, approved integrations, FERPA/privacy requirements, production hosting) are presented only as Phase-4 exploration, not as completed or committed work.

## Before presenting

- Rehearse once with a timer (8:00 hard stop). Press `F` for fullscreen.
- Have the live app already running and logged in so the Slide 5 handoff is instant.
- Keep a short backup screen recording of the demo in case the network drops.
