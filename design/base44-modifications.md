# Base44 (CARDREALM app) — modification plan

**Status:** inventory done 2026-10-12 (read-only public pass);
modifications are proposals — nothing is applied to the live app
without Joshua's go-ahead on that item. Base44 edits are live edits;
there is no staging branch, so changes are made deliberately, one at
a time.

## Intended role (Joshua, 2026-10-12)

CARDREALM (this app) will eventually be **the default viewer and the
on-profile representation of each player's entire collection across
all Mythos gaming card games**. The registry is the source of truth
behind it; this app is where a player's cross-game collection lives
visually. Every modification below serves that end state.

## Inventory (verified 2026-10-12, signed out)

- App: `omni-card-view.base44.app`. In-app branding is **CARDREALM**;
  browser tab, PWA manifest, and Apple app title still say
  **"OmniCard AR"** — a leftover name.
- Routes:
  - `/` → splash ("SUMMONING REALM" loader) → redirects to `/start`.
  - `/start` — landing: Sign In / Create Player tabs, "Scan a Card"
    link, a "MORE FROM US" info card (**copy only, zero links**),
    footer "PHYSICAL · DIGITAL · ARG".
  - `/collection` — gated: "Sign in to view your collection."
  - `/scan` — gated: "Sign in to add cards."
  - `/settings` — **fully public**: sound/music + HD rendering
    toggles, offline-cache note, INFO box (version v1.0.0, "3D viewer
    companion", data-driven card templates), and a **"System
    diagnostics & developer access"** expander gated by an ACCESS
    CODE (not attempted).
  - `/card/:id` — **not gated**: real card pages open directly by ID.
    An invalid ID shows "That card was not found in the realm."
    No valid public ID was discoverable signed-out (the one known ID,
    from Oct 10, is `6ac9d0272035a0c4988f26c5`).
- **Sign-in is the app's own Player ID system** — format
  `CR-XXXX-XXXX`, generated from a display name on Create Player.
  No email/password, no OAuth. This is a third identity silo next to
  Wix members and the game's Firebase players.
- **No external links anywhere** in the app UI — no Wix membership,
  no Gumroad, no socials.
- Settings INFO copy implies **official game data is not yet
  connected**: templates await art, models, and media.
- Data concepts visible: Player (display name + ID), per-player
  Collection, Card (addressable at /card/:id, added via Scan),
  physical packs, digital collectibles, on-chain tokens, ARG
  fragments. Base44 platform: a User entity auth check is present.
- Minor breakage: unknown multi-segment paths render a blank page
  instead of the 404 page.

## Editor audit (2026-10-12, signed-in session)

- ✅ **Rename done and published:** app title "OmniCard AR" →
  "CARDREALM" (Dashboard → Overview → Edit title), saved and
  published live. The single title field drives tab title and app
  name; no separate PWA/manifest name fields exist in settings.
  No other settings, content, or data were changed.
- **Entities (exactly 3):**
  - `Card` — **13 records.** Fields: serial_number (required),
    name, card_type (Creature, Spell, Artifact, Land, Token, Meme,
    NFT), cost, rarity (Common, Uncommon, Rare, Mythic, Legendary,
    Secret), attributes, art_prompt, art_url, model_url, audio_url,
    video_url, token_address, token_id, arg_fragment, batch_id,
    in_library (bool).
  - `Player` — 1 record. Fields: player_id (required), display_name,
    token_balance, nft_count, is_programmer (bool), created_date.
  - `PlayerCard` — **0 records.** Fields: player_id (required),
    card_serial, acquired_date, verified (bool).
- **Gaps vs. the registry model:**
  - Base44 `Card` fuses definition + instance in one record; the
    registry separates them. Join key: `serial_number` → instance;
    name/type/cost/rarity/attributes → the definition.
  - Type taxonomy differs: Base44 uses generic TCG types
    (Creature/Spell/…), MYTHOS uses its own (Abomination, Character,
    …). Registry rarity set lacks Base44's "Legendary".
  - `PlayerCard` is empty — ownership linking has never been used.
    The registry side of the link (`link_player_id`, email join) is
    built; the app still needs an "enter your email" screen.
  - `Player.token_balance` / `nft_count` have no registry counterpart
    yet (ledger-derived in the registry; do not mirror blindly).

## Proposed modifications (in order)

1. **Editor data audit (read-only first).** ✅ DONE 2026-10-12 —
   see "Editor audit" above. Gap list is in that section; entity
   changes still need Joshua's approval per item.
2. **Branding fix.** ✅ DECIDED 2026-10-12: rename "OmniCard AR" →
   CARDREALM everywhere (PWA manifest, tab title, app titles).
   In-app branding is already CARDREALM. Zero-risk, do first in the
   editor.
3. **External links.** Wire the "MORE FROM US" card (and/or /start)
   to the Wix membership page and Gumroad — the ecosystem currently
   has no doors between its rooms.
4. **Domains.** Confirmed 2026-10-12: **mythosgaming.dpdns.org**
   belongs to **all games** (the game side), and **mythosportal**
   (written by Joshua as "mythosPortal.pddns.org" — provider
   spelling to confirm, cf. dpdns.org above) will be **the home of
   the membership site** — not this app's domain. This app's own
   custom domain is TBD; the membership site at mythosportal is what
   links members here.
5. **Identity link.** ✅ DECIDED 2026-10-12: the player enters their
   member email in-app once to link their Base44 Player ID to the
   registry player (`players.externalIds.base44`). The registry
   matches on email (the same join key as the Gumroad pipeline);
   no link codes.
6. **Registry as data source.** Feed official card data into the
   app's templates — cheapest first: scheduled export from the
   registry into the app's data; live API calls only if Base44
   supports them cleanly. The Temp's Base44 values get classified as
   canon vs. game profile as part of this.
7. **Catalog the real cards.** Card pages are ungated by ID — with a
   Player ID sign-in (collection) or a list of card IDs, pull every
   card into the registry.
8. **Fix the blank-page 404** for unknown multi-segment paths
   (cosmetic; do last).

## Ground rules

- Read-only until Joshua approves a specific change.
- One change at a time, verified in the published app before the next.
- The original game (MYTHOS) and its backend stay untouched — this
  plan only concerns the Base44 app.
- The Settings diagnostics ACCESS CODE is Joshua's to enter (browser
  takeover) if developer access is ever needed — never shared in chat.


## Applied 2026-10-12 (Joshua's directive: full deck + alignment)

The inventory above is the pre-change snapshot. Applied since:

- ✅ **Full MYTHOS deck uploaded** via editor CSV import (dataset:
  `exports/base44-cards.json`): 59 new Card records; the 13 existing
  records untouched (a duplicate deck-version Temp created by the
  all-or-nothing import was soft-deleted to Trash; the canon Temp
  record stands). Card total: **72**. The Base44 API exists
  (token + bulk endpoint) but was not used; CSV import was the best
  in-session route.
- ✅ **card_type options extended** via builder: Character,
  Abomination, Ritual, Location, Action, Trap, Effect added; all
  original options kept.
- ✅ **Registry rarity aligned:** `legendary` added to the registry
  schema enum (Base44 already had it); 60/60 cards revalidated.
- ✅ **Membership link:** /start "MORE FROM US" now links
  "Membership" → the Wix membership page; verified live. (The game
  itself contains no Gumroad link anywhere — checked modal, HTML,
  and scripts — so none was added.)
- ✅ **Identity-link screen:** Player entity gained optional
  `member_email`; /settings has a "Link your membership" section
  storing the email on the signed-in player's record (local-storage
  fallback). Registry submission activates at registry deploy via
  `link_player_id` (APP_LINK_SECRET lives in a backend, never the
  app frontend).

Remaining from the original list: blank-page 404 fix (minor), and the
registry data feed / cross-game collection view (the end-state role
above), which follows the registry deploy.
