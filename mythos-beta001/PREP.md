# MYTHOS Beta 0.01 — Prep: Card Viewer + UI Declutter

**Status: PREPARATION ONLY.** Everything here is a local working copy and a set of
proposals for Joshua's approval. The live game (JustWiggleit/sturdy-eureka,
GitHub Pages) was not modified, and nothing has been deployed or pushed anywhere.
All design ideas below are **PROPOSALS**, not decisions.

Working folders:

- `original/` — local mirror of the game's served files (see fidelity notes).
- `preview/` — the same mirror plus the card-viewer prototype and two
  zero-judgment CSS duplicate removals (items D1/D2 in §5).

---

## 0. Mirror fidelity — read this first

Files were fetched from the repo's public sources. The fetch channel available
for this prep normalizes whitespace in some routes and **corrupts HTML embedded
inside JavaScript template literals**, so fidelity varies by file. Honest
per-file status:

| File | Mirror status |
|---|---|
| firebase-config.js | **Byte-exact** (verified against repo blob SHA) |
| net.js | **Byte-exact** (SHA-verified) |
| decks.json | **Byte-exact** (SHA-verified) |
| firebase.js | **Byte-exact** (SHA-verified) |
| index.html | Content-complete reconstruction (7,671 B vs 7,672 B source; likely one trailing-newline difference). Structure, ids, and text verified against two independent reads. |
| ai.js | Content-faithful reconstruction (12,753 B vs 12,852 B source; whitespace normalized). Passes `node --check`. |
| style.css | Content-complete reconstruction (20,772 B vs 20,763 B source). Every selector/declaration present; whitespace normalized. |
| cards.json | Content-verified reconstruction (compact formatting; 23,659 B vs 25,700 B pretty-printed source). Validated: parses, 60 cards, ids 1–60, type tally matches (Character 12, Abomination 32, Ritual 6, Location 3, Action 3, Trap 2, Artifact 1, Effect 1); cross-checked against two independent extractions. |
| data.js | Regenerated from the verified cards.json + decks.json in the source's own shape (`window.MYTHOS_DATA` with cards, decks, imgDir, cardBack, version); content matches both independent extractions. |
| **ui.js** | **NOT mirrored.** The fetch channel mangles the HTML inside its template literals, so a faithful copy could not be produced this way. It was read in full for the inventory in §2/§3 (function names, element ids, and flow are legible; exact template markup is not guaranteed). Canonical copy remains in the repo. |
| **engine.js** | **NOT mirrored** (56,658 B of pure game logic; read for its state shape and API surface, which is all the UI work depends on). Canonical copy remains in the repo. |
| assets/ (binary) | **NOT mirrored** — images cannot transit the text fetch channel. Contents: `assets/card-back.webp` (186,158 B) and `assets/cards/001.webp` … `060.webp` (one per card, named by each card's `img` field). |
| README.md, builder/ | Repo documentation and build tooling (builder generates data.js from cards.json/decks.json); not served game files, not mirrored. |

---

## 1. File inventory (served game, repo `main`)

| File | Size (source) | Role |
|---|---|---|
| index.html | 7,672 B | Page shell: loader, start screen, game-screen containers (`#board`, `#pending`, `#log`), and the static modals (`#detail`, `#zoom`, `#auth-modal`, `#popup`, `#toast`). Loads all scripts in order. |
| style.css | 20,763 B | All styling: palette variables, start screen, game chrome, player zones, card presentation (incl. 3D flip), modals, auth, popup, drag & drop, draw animation, 5 responsive breakpoint blocks. |
| data.js | 24,378 B | Embedded data: `window.MYTHOS_DATA` = 60 card defs + 2 prebuilt decks + `imgDir`/`cardBack`/`version`. The game's offline-first data source. |
| cards.json | 25,700 B | The same 60 card definitions as standalone JSON (source data the builder embeds into data.js). Fields: id, num, name, title, type, cost, control, sanity, power, flesh, leash, upkeep, rules, flavor, img (card 8 also carries `provisional_stats: false`). |
| decks.json | 894 B | The two prebuilt decks (Cult of the Worshiper; The Board's Hostile Bid), 45 card ids each. |
| engine.js | 56,658 B | Pure game logic (`window.MYTHOS`): state, phases, combat, rituals, card effects. No DOM. API used by ui/ai: setDefs, newGame, startGame, mulligan, nextPhase, canPlay, playCard, setTrap, ritualInfo, performRitual, activatedInfo, activate, releash, upkeepList, upkeepAction, canAttack, declareAttacker, undeclareAttacker, canBlock, declareBlocker, resolveCombat, legalTargets, decide, discard, effPower/effFlesh/effControl/effUpkeep/playCost/freeControl. |
| ai.js | 12,852 B | Heuristic opponent (`window.MYTHOS_AI`): mulligan/upkeep/main/declareAttacks/assignBlockers/discardDown/decide, driving the engine's public API. |
| ui.js | 62,382 B | All rendering and interaction (`#board` is fully re-rendered from engine state on every action): screens, modals, popups, toasts, drag & drop, draw animations, member badge, auth-modal wiring, `window.MYTHOS_TEST` hooks. Holds `WIX_LOGIN_URL` and `REPORT_EMAIL` constants. |
| net.js | 1,737 B | Online adapter stub: `OnlineAdapter` throws "not connected in v1"; `LocalAdapter` wraps local engine+AI. No online play. |
| firebase-config.js | 543 B | Firebase project config for the live game project (`window.MYTHOS_FIREBASE_CONFIG`). |
| firebase.js | 7,764 B | `window.MYTHOS_FIREBASE`: anonymous + email auth, `players/{uid}` profiles with serial ids, ownedCards collection grants, claim codes, membership tiers (cultist/operative/overlord), offline-first localStorage cache + Firestore sync. |
| assets/card-back.webp | 186,158 B | Card back art. |
| assets/cards/*.webp | 60 files | Card art, one per card. |

Third-party (CDN, not mirrored): Firebase compat SDK 10.12.2 (app/auth/firestore).

---

## 2. UI inventory — screens, panels, modals, HUD, controls

### 2.1 Loader (index.html, dismissed by ui.js `hideLoader()`)
- `#loader` (fixed, z-index 9999): game title, subtitle, spinner (`#loader-spinner`), status line `#loader-text`, hidden `#loader-error` panel with a **Report a problem** button (`#loader-report` → ui.js `reportIssue()`, opens a pre-filled mailto).
- An inline error-trap script in index.html captures early errors into `window.__mythosErrors` and can surface the error panel before ui.js loads.

### 2.2 Start screen (`#start-screen`, static HTML; dynamic bits via ui.js)
- `.title-block`: H1 title, `.subtitle`, `.tagline`.
- `.deck-pick`: two `.deck-card` panels (names filled from data: `#deck-a-name`, `#deck-b-name`) with a `.vs` divider — deck choice for both seats.
- Three `.mode-btns` rows, six actions total:
  1. `#start-login` (`.login-btn`) — opens the auth modal; `#start-guest` — play as guest.
  2. `#start-hotseat` — 2-player local; `#start-ai` — play vs AI.
  3. `#start-report` (`.report-btn`) — issue report (mailto).
- `#member-badge` (hidden until signed in; ui.js `refreshMemberBadge()` / `memberBadgeHTML()`): member tier + sign-out link.
- `details.howto`: collapsible "How to play — the short version" (11 rule bullets).
- `.foot`: one-line footer (AI/hotseat note, membership link).

### 2.3 Game screen (`#game-screen`; everything inside `#board` is rendered by ui.js `renderBoard()` on every state change)
- `#topbar` (sticky, z 20): `.game-title`; `.turn-info` ("Turn N · player name (YOU) · **Phase**"); `#member-chip` (member tier / Guest, sign-out); `.topbtns`: `#btn-log` (toggle log), `#btn-restart` (confirm → reload), `#btn-next` (advance phase).
- `#phase-banner`: one-line instruction for the current phase (ui.js `phaseBanner()`, different text per phase).
- Player zones `.pzone.foe` / `.pzone.me` (ui.js `playerZoneHTML()`):
  - `.phead`: player name, `.sanity` (◈ count), `.deckpile` (card-back thumbnail + deck count), `.discardpile` (🗑 + count; also a drag-drop target), hand count, `.rituals` (☽ n/3, only when > 0), `.shield` (🛡, only when active).
  - `.field` with `.field-label` ("ENEMY FIELD" / "YOUR FIELD") and `.field-cards`: `.chars` (`.char-group`: character card + its `.leashed` abominations), `.aboms-loose` (unleashed/feral), `.perms` (locations/artifacts/effects), `.traps` (face-down card backs + count + `.trap-note`).
  - `.hand`: opponent's hand as card backs; own hand as playable cards.
  - `.upkeep` panel (own zone, upkeep phase only; `upkeepHTML()`): per-abomination mini row with Pay / Skip / Stapler buttons (`data-act`).
- `#midbar` (static container in index.html; content by `midBarHTML()`): usually **empty**; shows `.combat` attacker→target list during combat, `.target-banner` while targeting (with `#btn-cancel-target`), a discard-mode banner (with its own `#btn-next2` phase button) during end-phase discard. The **⚔ Resolve combat** button (`#btn-resolve`) is *not* rendered here — a `setInterval` poller in ui.js (every 400 ms) injects/removes it.
- Card presentation (ui.js `flipWrap()`, `boardCardHTML()`, `charHTML()`, `handCardHTML()`): `.card3d` flip wrapper (front art / back art); `.bcard` on board with `.bstats` caption line and `.flag` badges (FERAL / BURNED OUT / ASLEEP); `.hcard` in hand with a circular ▶ quick-play button (`.playbtn`); state classes: playable, sel, feral, burned, asleep, attacking, blocking. Interactions: click (context action / detail), double-click (zoom), long-press 350 ms (drag to field or discard pile, `.drag-ghost`), shift/long-press variants documented in code comments.

### 2.4 Modals and overlays
- `#detail` (z 70; `#detail-close`, `#detail-body`): card detail (ui.js `openDetail()`) — large art (dblclick → zoom), `.dinfo`: name, `.dtitle`, `.dtype` (type + stat line), `.drules`, `.dflavor`, and a `.dbtns` action row that varies by context (Play / Set trap / Perform ritual / Activate ability / Re-leash / Attack / Flip / Close) plus a `.btn-why` line explaining why an action is unavailable. **The same `#detail-body` is reused as the host for two other flows**: the leash picker (`leashModal()`) and the ritual picker (`ritualModal()`).
- `#zoom` (z 70; `#zoom-close`, `#zoom-img`): full-size art view; opened by double-clicking any card image.
- `#auth-modal` (z 80): member sign-in — `#auth-title`, `#auth-sub`, `#auth-email`, `#auth-pass`, hidden `#auth-error`, `#auth-submit`, `#auth-toggle` (sign-in/sign-up switch), `#auth-guest` (continue as guest), `#auth-wix` (link out to the Wix membership page; target is ui.js's `WIX_LOGIN_URL`). Wired to `MYTHOS_FIREBASE` email/guest flows.
- `#popup` (z 90; `#popup-close`, `#popup-msg`, `#popup-info`, `#popup-ok`): the instructional modal (ui.js `popUp()`). Used for errors, phase instructions, and confirmations; the Info button swaps in rule text from `RULE_INFO` (14 topics: draw, upkeep, main, attack, defend, resolve, end, sanity, rituals, leash, traps, mulligan, flip, drag). First entry into each phase per match triggers a `PHASE_INTRO` popup (`maybePhasePopup()`); popups auto-dismiss after 2.5 s only during AI turns.
- `#pending` (z 60; content by `renderPending()`): full-screen decision overlay for engine pending states — 9 kinds: The Temp's contract (pay/return), HR Complaint (pay/sacrifice), Wisp discard pick, Coffee Elemental heal pick, Full-Timer promotion, Restructurer location pick, Mimic top-card choice, Auditor hand reveal, sleep target pick.
- `#toast` (z 100): transient bottom-center message (`toast()`, ~2.6 s): draw announcements (with card names), AI play summaries (with sanity totals), phase tallies.
- `#log` (z 50): fixed bottom-right panel, last 60 log entries (`renderLog()`), toggled by `#btn-log`; re-filled on every render.
- Setup/mulligan screen (rendered into `#board` by `renderSetup()`): `.setup-box` with the opening hand, `#btn-mulligan` / `#btn-keep`; in hotseat, a "pass the device" note for player 2.
- Game-over screen (rendered into `#board` by `renderGameOver()`): winner headline (YOU WIN / THE AI WINS / name WINS), win reason, turn count, play-again (reload).
- Transient elements: `.draw-fly` (card-back flight animation deck→hand, queued by `pumpDrawQueue()`), `.drag-ghost`, `just-drew` glow on drawn cards.

### 2.5 Data/member surfaces outside the board
- Start-screen `#member-badge` and in-game `#member-chip` are two renderings of the same membership state (ui.js `memberBadgeHTML()`), each with its own sign-out binding (`bindBadgeSignout()`).

---

## 3. Clutter findings (with code evidence)

**F1 — Three competing notification channels, with the same events announced in several of them at once.**
`#popup` (modal, blocks until OK on human turns), `#toast` (bottom-center, 2.6 s), and `#log` (fixed panel) all carry game events; `#phase-banner` and `#midbar` banners add two more text surfaces. Concretely: entering a phase fires a `PHASE_INTRO` popup *and* updates the always-visible `#phase-banner` with near-identical wording (ui.js `maybePhasePopup()` + `phaseBanner()`); drawing fires a toast naming the cards *and* a log entry *and* a fly animation (`announceDraws()`); AI plays fire a summary toast *and* log entries (`aiStep()`).

**F2 — The log panel overlays the play area.**
`#log` is `position: fixed; right: 10px; bottom: 10px; width: min(420px, 90vw); max-height: 40vh; z-index: 50` (style.css) — when opened it floats over the bottom-right of the board, which is where the viewing player's own zone and hand render. On short screens it can cover hand cards. It has no docked home; it's a floating window competing with the board.

**F3 — `#midbar` is an always-present strip that is empty most of the time, and its one critical button is injected by a polling timer.**
`#midbar` has `padding: 6px 14px; min-height: 8px` (style.css) and `midBarHTML()` returns an empty string unless there are attackers, an active targeting state, or discard mode — so in most phases it's a dead band between the phase banner and the enemy zone. Meanwhile the Resolve-combat button, the most important control of the resolve phase, is not part of the render pipeline at all: a `setInterval(..., 400)` in ui.js polls the state and appends/removes `#btn-resolve` out of band.

**F4 — Duplicated and scattered CSS rules.**
- `.bcard img, .hcard img { width: var(--card-w) }` is declared twice (cards section, then again in the responsive section under "card images use the variable").
- `.member-chip { display: none }` is declared in two places (the portrait media query, and a trailing one-line `@media (max-width: 480px)` block at the very end of the file).
- `--card-w` is redefined in six separate `:root`/media blocks, so the card-size system is spread across the whole stylesheet.
- The toast styles carry a leftover comment "(existing toast styles retained below for transient status only)" — archaeology in the stylesheet.

**F5 — The start screen stacks six actions of mixed importance in three same-weight rows.**
Login (its own blue `.login-btn` style), Play as guest, 2-player hotseat, Play vs AI, and Report a problem (its own red `.report-btn` style) all sit in `.mode-btns` rows between the deck pickers and the how-to — account and support actions visually compete with the primary "start a match" actions, and the member badge appears/disappears in the same stack (index.html; style.css `.login-btn` / `.report-btn` / `.mode-btns`).

**F6 — One modal hosts three different flows, and mixes reading with acting.**
`#detail-body` renders the card detail (`openDetail()`), the leash picker (`leashModal()`), and the ritual picker (`ritualModal()`). The card detail itself combines reference content (art, rules, flavor) with up to seven context-dependent action buttons plus an error line (`.btn-why`), so the same surface is both the game's "look at a card" view and its main action menu — hard to predict what opening a card will show.

**F7 — A tall stack of fixed overlays with interleaved z-indexes.**
Loader 9999, drag-ghost 210, draw-fly 200, toast 100, popup 90, auth 80, detail/zoom 70, pending 60, log 50, topbar 20 (style.css). Because toast (100) outranks popup (90) and pending (60), transient messages can appear *above* decision modals that are waiting for input; and the draw animation deliberately has to wait for popup dismissal (`pumpDrawQueue()` checks popup visibility) — the channels are already fighting in code, not just visually.

**F8 — The player header packs six-plus data items into one undifferentiated row.**
`.phead` (ui.js `playerZoneHTML()`, style.css) renders name, sanity, deck pile + count, discard pile + count, hand count, ritual progress, and shield inline on one baseline with mixed icon vocabularies (◈, 🗑, ☽, 🛡, 🂠). Everything is the same visual weight, so the one number that matters most (sanity — it's also the life total) doesn't stand out.

**F9 — Constant 3D motion/tilt competes with readability.**
`#board` has `perspective: 1600px`; the enemy zone is permanently tilted `rotateX(6deg) scale(.97)`, the player zone `rotateX(-2deg)`; every card hover lifts `translateZ(26px)` and selections/attackers `translateZ(44px)` (style.css). Two media queries then have to flatten all of it back out for small/landscape screens — evidence the effect already fights the layout.

**F10 — Membership state is rendered twice, in two places, with duplicated wiring.**
`#member-badge` (start screen) and `#member-chip` (topbar) render the same `memberBadgeHTML()` and each binds its own sign-out handler; on narrow screens the chip is `display: none` (twice — see F4), so in-game membership state simply vanishes on phones.

---

## 4. Card viewer design — PROPOSAL

**Goal (from Joshua's order):** a viewer for the full 60-card set, inside the game's
own presentation, fed only by data the game already has. No new backend.

- **Entry point:** a new "🃏 Card Viewer" button on the start screen, in the first
  `.mode-btns` row next to Login/Guest (it is a pre-game, browsing activity like
  the how-to). Optionally also a small "Cards" button in the in-game `.topbtns`
  (read-only; a match in progress is untouched — the viewer never reads or
  writes engine state).
- **Browse grid:** all 60 cards from `window.MYTHOS_DATA.cards`, each tile
  rendered with the game's own card presentation — the same flip-card art
  treatment (`.card3d`/`.bcard`) and the same stat-line format the board uses
  (`statLine()` in ui.js: Cost/Ctl/San for Characters, Cost/P/F/Upk for
  Abominations, Cost otherwise). Sorted by collector number (`num`), as in
  cards.json.
- **Detail view:** clicking a tile opens the game's existing detail layout
  (`.dinfo`: name, title, type + stat line, rules, flavor — the `openDetail()`
  structure) in **read-only** form: no Play/ability buttons, plus the collector
  number and a full stat row (every non-null field). Flip (front/back) and
  double-click zoom reuse the game's existing patterns. Prev/Next stepping
  through the filtered list.
- **Type filter:** a chip row — All (60) + Character (12), Abomination (32),
  Ritual (6), Location (3), Action (3), Trap (2), Artifact (1), Effect (1) —
  counts from the data. (The prototype also adds a name search box; that's a
  bonus, not part of the core proposal.)
- **Data:** `window.MYTHOS_DATA` only — the same embedded data the game boots
  with. Works offline; art resolves to the local `assets/cards/` in the real
  build. No Firebase, no registry calls. (A later phase can overlay
  CARDREALM/registry ownership onto this same grid; explicitly out of scope
  for Beta 0.01 prep.)
- **Placement options:** (a) an in-page view swapped like `#start-screen` /
  `#game-screen` — best long-term fit; (b) a standalone `viewer.html` page —
  what the prototype ships (see §6) because ui.js could not be mirrored
  faithfully, making in-page integration unsafe to prototype blind.

## 5. Declutter plan — PROPOSAL (presentation-only)

Each item: current state → proposed change → risk. **No gameplay, rules,
balance, net, Firebase, or membership behavior changes anywhere in this list.**
Items D1–D2 need no design judgment and are **already applied in `preview/`**
(nowhere else). Everything else is awaiting Joshua's approval.

- **D1 — Duplicate card-width rule.** Current: `.bcard img, .hcard img { width: var(--card-w) }` declared twice. → Remove the second declaration. → Risk: none (identical rule). **[Applied in preview/style.css]**
- **D2 — Duplicate member-chip rule.** Current: `.member-chip { display: none }` in two media blocks. → Remove the trailing duplicate. → Risk: none. **[Applied in preview/style.css]**
- **D3 — Consolidate card-size variables.** Current: `--card-w` redefined in six `:root`/media blocks scattered through style.css. → Gather them into one commented breakpoint table (same values, one place). → Risk: low — a value typo would rescale cards at one breakpoint; diff-check values when applying.
- **D4 — Give the log a docked, non-overlapping home.** Current: `#log` floats over the board's bottom-right when open (F2). → Dock it as a collapsible strip under `#midbar` (in-flow, pushes the board down instead of covering it), or cap it to the right margin column on wide screens. → Risk: low; in-flow docking shifts board position when opened — acceptable, and only when the player opens it.
- **D5 — Collapse the empty `#midbar`.** Current: dead band in most phases (F3). → Zero padding/min-height when it has no content; restore spacing only when a banner is present. → Risk: low; slight layout shift when combat starts — the phase where attention is already on the midbar.
- **D6 — Render the Resolve button in the render pass, not by polling.** Current: 400 ms `setInterval` injects `#btn-resolve` out of band (F3). → Include it in `midBarHTML()` when phase/attackers state requires it (same visibility rule). → Risk: medium-low — it touches ui.js's render flow (behavior-preserving in intent: same button, same condition, same handler), so it should be verified against the resolve flow in playtest. Flagged as the one item that is code-adjacent rather than pure CSS.
- **D7 — Tier the start-screen actions.** Current: six same-weight actions in three rows (F5). → Primary row: Play vs AI / 2-player hotseat (large). Secondary row, visually quieter: Login / Play as guest. Move Report a problem down beside `.foot`. → Risk: low — login becomes slightly less prominent; keep it labeled "🔑 Login (members)" so members still find it immediately.
- **D8 — Pick one phase-guidance channel.** Current: `#phase-banner` text and `PHASE_INTRO` popups duplicate each other (F1/F7). → Keep the banner as the persistent instruction; make phase popups first-*run*-only (per player, via localStorage) instead of first-time-per-match, with the how-to remaining the reference. → Risk: medium-low — new players mid-first-match get less hand-holding; the banner + how-to still cover it. Joshua's call on which channel survives.
- **D9 — Reserve the popup modal for decisions and errors.** Current: informational messages also route to `#popup`, while toasts can stack above it (F1/F7). → Info-only messages (AI summaries, draw notes) go to toast/log only; `#popup` appears only when the player must acknowledge or choose. → Risk: low — presentation routing only; a few ui.js call sites change which channel they call.
- **D10 — Group the player header.** Current: six-plus items in one row (F8). → Two clusters: (name + sanity, emphasized) and (piles/counts/rituals/shield, dimmer), with one consistent icon style. → Risk: low — markup order in `playerZoneHTML()` + CSS grouping; no data changes.
- **D11 — Calm the 3D tilt.** Current: permanent zone tilt + hover lift everywhere (F9). → Reduce foe tilt to ~3deg and drop the hover `translateZ` lift on touch devices (keep it for mouse). → Risk: low, but it changes the game's "feel" — purely Joshua's taste call.

## 6. Prototype (`preview/`)

- **Form: standalone page** (`preview/viewer.html` + `preview/viewer.js`),
  loading the mirrored `data.js` and `style.css`. **Why not integrated:**
  ui.js (which owns screen-swapping and the start-screen buttons) could not be
  mirrored faithfully through the fetch channel (§0), so editing the game's
  page blind would risk exactly the kind of silent corruption this prep exists
  to avoid. The standalone page proves the full viewer against the game's real
  data and styles; integration is a small, reviewable step once ui.js is
  available byte-exact (e.g. from a repo clone).
- **What it does:** filter chips for All + 8 types with counts; name search
  (bonus); a grid of all 60 cards using the game's card presentation (art +
  `.bstats` stat line in ui.js's `statLine()` format); click → detail modal in
  the game's `.dinfo` layout (name, title, type + stats, collector number,
  full stat row, rules, flavor) with Flip (card back), Prev/Next, double-click
  zoom, Esc/arrows. If card art can't load, a tile falls back to a text face
  built from the card's data (the binary assets aren't mirrored — §0 — so art
  is referenced from the live Pages site; offline, the fallback keeps the
  viewer fully usable).
- **Declutter applied:** only D1 and D2 (exact-duplicate CSS removals, marked
  with comments in `preview/style.css`). Nothing else was changed.
- **Verified:** headless smoke test — grid renders 60 tiles, filter bar builds
  9 buttons, search "temp" narrows to exactly card 14 (The Temp), detail view
  shows name/type/stats/rules/flavor; all files serve 200 over a local static
  server.
- **How to open:** either double-click `preview/viewer.html` (file:// works —
  classic scripts only, no fetch), or serve the folder:
  `python3 -m http.server 8901 --directory ~/workspace/mythos-beta001/preview`
  then open `http://localhost:8901/viewer.html`. (The mirrored `index.html`
  in preview/ will sit on its loader: its boot code lives in ui.js, which is
  not mirrored — see §0. The viewer does not depend on it.)

---

*Prepared for Joshua's review. Nothing in §4–§5 has been decided; D1–D2 are
the only changes made anywhere, and only inside `preview/`.*
