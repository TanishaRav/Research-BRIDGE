---
inclusion: always
---

# ResearchBridge product design and frontend engineering standard

This is the persistent, binding form of the supplied 24-section standard. Domain requirements in the ResearchBridge spec refine generic examples, but never weaken accessibility, truthful functionality, privacy, or quality safeguards.

## 01. Role and execution standard

Work as a principal product designer and senior frontend engineer. ResearchBridge supports fair, explainable EUReCA batch matching for students, faculty, and administrators. The result must feel intentionally designed and iterated rather than assembled from a dashboard template. Favor clarity over decoration and craftsmanship over visual complexity. Every layout, interaction, transition, and component needs a task-related purpose.

## 02. Absolute anti-template rules

Do not use generic purple/blue gradients, neon or gradient text, glowing orbs, blobs, decorative shapes, excessive glass or blur, generic three-card feature grids, circular colored icon containers, nested cards, indiscriminate pills, giant in-app marketing headings, welcome banners, “AI-powered” promotion, sparkles, random emoji icons, whitespace that hides missing substance, forced symmetry, unnecessary badges, a card around every section, borders around every element, unmodified Tailwind/shadcn/Material defaults, testimonials, fabricated metrics, single-number oversized cards, routine circular spinners, or capability-showcase animation. If a decision resembles common generated SaaS UI, simplify or redesign it.

## 03. Color and surfaces

Use semantic tokens. Core palette: canvas `#FBFBF9`, primary surface `#FFFFFF`, secondary surface `#F4F4F0`, primary text `#191919`, secondary text `#525252`, muted text `#6B6B6B`, divider `#E5E5E0`, and the single brand accent `#A6192E`. Reserve accent for selected states, important information, and primary actions. Define success/warning/error/info separately and pair color with text/icon/status. Define hover, active, selected, disabled, destructive, and focus-visible tokens. Normal text must reach 4.5:1 contrast; large text and meaningful boundaries must reach 3:1. Subtle decorative separators need not identify controls. Avoid pure-black backgrounds, glaring large whites, and arbitrary grays.

## 04. Typography and editorial direction

Use Space Grotesk for headings and Public Sans for body, with optional JetBrains Mono for technical/numeric evidence. Bundle or use properly licensed sources and metric-compatible fallbacks to avoid layout shift. No Inter, Roboto, or unmodified system-default identity. Limit primary families to two. Use a deliberate scale: display 36–48 only where justified, page heading 28–36, section 20–24, component 15–18, body 14–16, support 12–13. Use controlled weight/letter-spacing, readable measures and line heights, left alignment, and tabular numerals. Avoid excessive bold, uppercase, and tracking. Typography must carry hierarchy without color.

## 05. Layout, composition, and rhythm

Use a 4px foundation with 4/8/12/16/20/24/32/40/48/64/96 values. Build around information hierarchy, not available components. Use asymmetry where it improves focus. Group through negative space and shared grid lines. Keep predictable page margins. Prefer flat sections and subtle dividers; cards only for meaningful independent units and never card-inside-card. Use progressive disclosure. Balance density with readability and preserve geometry during load/update. Give every workflow its own appropriate composition rather than repeating one dashboard grid.

## 06. Component craftsmanship

Buttons need primary, secondary, tertiary, ghost, and destructive variants; action-specific labels; stable dimensions; consistent height/spacing; restrained radii; one dominant action per task area; icons only for recognition. Panels use subtle surfaces, 6–12px radii, hairlines, and no heavy shadows except overlays. Forms keep visible labels, required/optional markers, field-level actionable validation, entered values, native autocomplete/input behavior, logical grouping, and manageable length. Menus/dialogs need consistent placement, keyboard support, Escape, focus restoration/trap, viewport collision handling; dialogs are for focused or consequential decisions, not navigation. Use Lucide consistently at standard optical sizes; icon-only controls require accessible names; never substitute emoji.

## 07. Loading architecture

Do not use circular loading spinners for ordinary pages, data, or navigation. Use geometry-matched structural skeletons with realistic line lengths, rows, profile blocks, charts, and metadata. Keep shell/navigation/context visible. Use neutral static placeholders or restrained opacity pulse and disable animation for reduced motion. Avoid shimmer gradients. Prevent flashes for imperceptible requests and layout shifts on resolve. Tables retain headers and aligned skeleton rows. Refresh preserves existing content with discreet updating status. Pagination preserves geometry. Forms preserve button width, prevent duplicates, and give contextual feedback. Long operations show actual named stages and determinate progress only when measurable; never invent percentages.

## 08. Complete state design

Account for default, hover, pressed, focus-visible, selected, disabled, loading, empty, partial, error, success, offline, and permission-restricted states. Distinguish no data, no filter results, retrieval failure, and insufficient permission. Empty states explain what is missing and the next action without generic illustration. Errors are specific and recoverable. Success is brief and relevant. Preserve context.

## 09. Motion and microinteractions

Motion clarifies feedback and spatial change. Target 80–120ms immediate feedback, 120–180ms control transitions, 150–220ms popovers, and 200–280ms dialogs. Use consistent natural easing, transform/opacity when needed, and never block action. Prohibit bouncing cards, large hover scale, dramatic entrances, universal stagger, ordinary-dashboard scroll animation, routine full-page fades, and unnecessary layout animation. Honor `prefers-reduced-motion`.

## 10. Navigation and information architecture

Match the user’s mental model. Separate primary navigation from contextual actions, maintain stable placement and clear active state, and use breadcrumbs only for real hierarchy. Support meaningful deep links, URL-backed relevant filters, predictable browser history, and minimal nesting. Tabs are only for genuinely related views. Do not hide essential functions behind ambiguous icons. Every screen must communicate location, viewed object, available actions, consequences, and return path.

## 11. Tables, lists, and data presentation

Treat data components as first class. Align headers and columns, right-align comparable numbers, use tabular numerals, real sorting/filtering, visible filters, and pagination/virtualization where warranted. Preserve loading alignment; use subtle row dividers, restrained contextual actions, sticky headers only for long tables, consistent missing values, readable truncation with full access, and clear interactive-row affordance. Do not convert tables to giant card collections. Charts must answer a real question with direct labels, accessible colors, units, scales, and a table/text alternative. No arbitrary lines/donuts or unsupported metrics.

## 12. Search and filtering

Search actual relevant fields. Debounce where requests warrant it, expose recognizable affordance, active filters, individual removal, reset-all, accurate counts, keyboard operation, predictable sort, loading and no-result states. Persist state in the URL where useful. Avoid a request per keystroke and reveal advanced filters progressively.

## 13. Responsive design

Test 360, 390, 768, 1024, 1280, 1440, and 1920 widths. Prevent unintended page scroll, overlap, clipping, and hover-only controls. Use common touch targets of at least 44×44px, responsive type/spacing, functional mobile navigation, intentional table treatment, long-content resilience, browser zoom/text growth, safe areas, and virtual-keyboard awareness. Do not merely stack desktop components; reconsider priority and interaction at each breakpoint.

## 14. Accessibility

Target WCAG 2.2 AA. Use semantic HTML, logical headings, associated labels, complete keyboard access, visible focus, screen-reader-compatible controls, appropriate live regions, dialog focus management, sufficient contrast, reduced motion, meaningful alt text, accessible chart/table alternatives, logical reading/tab order, and a skip link. Prefer native HTML and avoid redundant ARIA or ARIA used to hide incorrect semantics. Validate with automated checks and manual keyboard use.

## 15. UX writing

Copy is concise, specific, neutral, actionable, consistent, and domain-appropriate. No promotional workflow language, “unlock,” “effortlessly,” “journey,” “supercharge,” “seamless,” vague “Oops,” or exclamation excess. State what failed and recovery, what is absent and next action, and precise consequences for confirmations/destructive actions.

## 16. Frontend architecture and quality

Use type-safe contracts, composable components, feature organization, centralized tokens, consistent names, presentation/state/business separation, explicit async/error/malformed-data handling, request cancellation, reliable invalidation, duplicate prevention, predictable lifecycle, and few dependencies. Add error boundaries where useful. Avoid monoliths, duplicated markup, arbitrary inline style, hardcoded token values, and abstractions without practical benefit. Accessible primitives are acceptable only after deliberate customization.

## 17. Real functionality

Every visible action works. No dead buttons, pretend forms, visual-only filters, empty search logic, nowhere links, fake notifications, generated analytics shown as real, hardcoded success, fabricated AI integration, or nonfunctional settings. If a backend is unavailable, use a deterministic schema-based mock and label simulation. Prefer fewer complete workflows over broad unfinished screens.

## 18. Data realism and integrity

Support long/short and duplicate names, missing imagery/descriptions, dates/time zones, zero/large values, incomplete profiles, permissions, conflicts, failures, and larger sets. Never assume clean data. Use only synthetic/anonymized sensitive-domain demos and do not leak data through logs, client environment, URLs, screenshots, or unnecessary UI.

## 19. Performance and perception

Measure where tools allow; do not claim unsupported field results. Targets at p75 are LCP ≤2.5s, INP ≤200ms, CLS ≤0.1. Reduce re-renders and client JavaScript, lazy-load noncritical expense, optimize fonts/images, avoid request waterfalls, cache correctly, preserve content during refresh, and virtualize only when useful. Optimistic updates need safe rollback. Never trade correctness for apparent speed.

## 20. Visual assets

Use imagery only when task-relevant. If photography becomes necessary, use grounded environments, consistent lighting/color/crops, and avoid generic corporate stock or artificial people. Never add illustrations as filler. Let typography, layout, controls, and real data communicate.

## 21. Security and privacy by design

The frontend is not a security boundary. Enforce server authorization, keep secrets out of client code, render user content safely, handle identity expiration where relevant, minimize personal information, use safe session practices for any future auth, communicate permission consequences, make destructive behavior explicit, and prevent accidental duplicate actions. Respect ResearchBridge’s synthetic-only and institutional-data boundaries.

## 22. QA and visual regression

Test every route/action/form/validation; loading/error/empty/partial states; keyboard and screen-reader behavior; slow/failing networks; mobile/tablet; long data; zoom; repetition; and browser history. Use automated component/e2e tests where practical. Capture supported widths and inspect spacing, alignment, wrapping, icon alignment, font weight, density, decoration, radii, stacking, and layout shift. Never report unexecuted checks as passed.

## 23. Mandatory process

Before implementation: establish workflows, information architecture, visual direction, tokens, components/states, data model/edges, and responsive behavior. During implementation: build shell and primitives; complete primary journeys; add loading/empty/error/permission states; refine response; validate accessibility; optimize. After implementation: inspect rendered UI; remove generated-template patterns; refine spacing/type/hierarchy; verify interactions; fix inconsistencies and edges; disclose remaining limitations. A pretty first draft is not completion.

## 24. Final acceptance

Completion requires coherent identity, functional major workflows, meaningful feedback, stable loading, useful empty/errors, supported responsive layouts, consistent typography/spacing, validated accessibility, measured performance where available, realistic edge data, maintainable code, and no decoration-only components or obvious generic generated patterns. ResearchBridge should feel quiet, confident, precise, purposeful, and well engineered. Refine existing work before adding ornament. Choose the simpler accessible solution when uncertain. A real product that is beautiful is the goal; beauty without real behavior is insufficient.
