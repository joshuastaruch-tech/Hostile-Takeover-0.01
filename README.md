# Hostile-Takeover-0.01
beta version online multiplayer test, no UI update

---

# Card Registry

**Status: Beta 0.01** (2026-10-12) — registry-integrated build. Objective:
both versions of the game access this database; the original live game
receives access via a later patch and is not modified until then.

Canonical card registry for the CARDREALM ecosystem: one source of truth for
what every card **is**, which copies exist, who owns them, and how each card
behaves in each game — physical, digital, and NFT.

The card viewer (`omni-card-view`) reads from the Registry API. This repo is
what gets linked to it: versioned card data, the database schema, the API,
and the per-game SDKs.

## Your stack

You're building on **Firebase + Wix + Google Sites**, so the deployed
backend is Firestore, not raw Postgres. The SQL migration stays as the
**logical model** (it's the clearest spec of the relations); `firestore/`
is the physical mapping you actually deploy:

- `firestore/data-model.md` — every table → collection, denormalization
  decisions (e.g. `currentOwnerId` on the instance replaces the SQL view),
  Cloud Function triggers, and the Wix / Google Sites wiring.
- `firestore/firestore.rules` — public reads for card data, append-only
  ledger, player-scoped entitlements, backend-only writes.

Identity comes from **Wix Members**: each `players/{uid}` doc stores the
`wixMemberId`, and a backend endpoint verifies the Wix session then mints a
Firebase custom token — one login across the site, the viewer, and the games.

The **Google Sites + AI blogger** page is the lore front door: embed viewer
card pages via Sites' Embed, and let the scheduled blogger job pull new
`flavorText`/ARG fragments from the registry to draft posts.

**Blockchain scope (Phase 1):** NFT ownership is validated *internally* from
the registry ledger — no wallets, no signature challenges. The *only*
blockchain interaction is anchoring a SHA-256 proof hash when a card is
reported stolen or destroyed. Wallet support comes in Phase 2.

## The model (three layers)

1. **Definition** — what the card is (`cards/*.yaml` → `card_definitions`).
   Versioned. Errata creates a new version; history is never rewritten.
2. **Instance** — which copy (`card_instances`). A physical print, a digital
   copy, and an NFT token are all *instances* of one definition. Serials
   live here, not on the definition.
3. **Ownership** — who held it when (`ownership_ledger`, append-only).
   Current owner is *derived* from the ledger, so provenance is never lost.

One definition → many instances → one owner at a time.

`game_card_profiles` is the multi-game hinge: it maps a definition into each
game's own stats and legality, so one canonical card can cost 9 in Arena,
cost 9 with different power in MYTHOS, and be banned in Odyssey — without
forking its identity.

## Layout

```
card-registry/
├── README.md                  # this file
├── schemas/
│   └── card-definition.schema.json   # validates every cards/*.yaml
├── cards/
│   └── the-temp.yaml                 # example: "The Temp" (v1)
├── migrations/
│   └── 001_initial_schema.sql        # logical model (Postgres) + seed data
├── firestore/
│   ├── data-model.md                 # physical model: collections, triggers, Wix/Sites wiring
│   └── firestore.rules               # security rules for the deployed DB
├── api/                       # (to build) Registry API service
│                              # implements the contract below
└── sdks/
    ├── python/
    │   └── card_registry.py          # client for Arena (Python)
    ├── web/                   # JS/TS client for MYTHOS (HTML5) — see sdks/web/README.md
    │   ├── card-realm-client.js   # browser client (no secrets; talks to your server)
    │   ├── registry-client-node.js# Node port of the Python SDK (server-side, API key)
    │   └── server-proxy.example.js# Express router wiring browser ↔ registry
    └── godot-unity/
        └── INTEGRATION.md            # hand this to Claude Code as-is
```

## API contract (what all three games code against)

Base: `https://registry.cardrealm.example` — API keys are **server-to-server
only**. Never ship a key in a client build (especially the HTML5 one).

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/cards?game={slug}&legal=true` | List definitions, optionally filtered |
| GET | `/v1/cards/{slug}?version=latest` | Definition + media slots |
| GET | `/v1/cards/{slug}/games/{game}` | Per-game profile (cost/power/legality) |
| GET | `/v1/instances/{id}` | Instance + current owner + NFT/physical links |
| GET | `/v1/players/{id}/entitlements?game={slug}` | What a player can field in a game |
| GET | `/v1/players/{pid}/ownership/{iid}` | 200 = owns, 404 = doesn't (fast check) |
| POST | `/v1/transfers` | Record sale/trade/mint/burn (signed, server-side) |
| POST | `/v1/claims` | Redeem a physical QR/NFC claim code |
| POST | `/v1/proofs` | Report stolen/destroyed → anchors proof hash on-chain |
| GET | `/v1/proofs?instance={id}` | Fetch anchoring proofs for an instance |

Game servers treat the registry as authoritative. **Never trust the game
client on ownership** — the client asks your server, your server asks the
registry.

## Game integrations

### 1. Arena — Python (on GitHub)

Use `sdks/python/card_registry.py`. Typical server flow:

```python
from card_registry import CardRegistry
reg = CardRegistry()  # reads CARD_REGISTRY_URL / CARD_REGISTRY_API_KEY

profile = reg.profile("the-temp", "arena")   # cost/power/legality for Arena
if profile["is_legal"] and reg.owns(player_id, instance_id):
    allow_in_deck(card)
```

Cache profiles in memory keyed by `(slug, ruleset_version)`; refetch when
the registry's `ruleset_version` for your game changes. Deck validation
happens on your server at match start, not in the client.

### 2. MYTHOS — HTML5 (online)

The browser client **never talks to the registry directly**. Flow:

1. Browser → your game server (session cookie).
2. Your server → registry (API key), same checks as Arena.
3. NFT path (Phase 1): no wallet connection. Your server validates ownership
   internally from the registry ledger — `owns()` rejects destroyed cards
   and surfaces stolen warnings — then grants the entitlement for MYTHOS.
   Wallet signatures arrive in Phase 2.

**MYTHOS is already mapped.** The repo (`JustWiggleit/sturdy-eureka`) holds
60 cards in `cards.json` with stats `control/sanity/power/flesh/leash/upkeep`:

- `scripts/import_mythos_cards.py` converts `cards.json` into `cards/*.yaml`
  (all 60 done, schema-validated). Re-run it whenever the game retunes cards;
  existing canon fields are preserved, only the `mythos` profile is rewritten.
- `sdks/web/mythos-registry.js` is a drop-in overlay: after `firebase.js`
  initializes, `MYTHOS_REGISTRY.sync()` pulls every `gameProfiles/mythos`
  doc in one query and `applyAll(MYTHOS_DATA.cards)` overlays cost, stats,
  legality and rules patches onto the embedded data. Offline, the game just
  uses its embedded cards. No secrets, public reads only.
- Worked example: **The Temp** is cost 9 in the CARDREALM canon but cost 2
  in MYTHOS with `power 2 / flesh 2 / leash 1 / upkeep 1` and a game-specific
  rules patch — exactly what `game_card_profiles` was designed for.

This keeps the API key and the ownership decision off the client entirely.

### 3. Odyssey — Godot / Unity (Claude Code)

Hand `sdks/godot-unity/INTEGRATION.md` to Claude Code verbatim, with this
repo checked out. It contains the endpoint contract, example payloads, the
ownership/entitlement flows, and caching rules — everything an agent needs
to write the `HTTPClient` (Godot) / `UnityWebRequest` (Unity) integration.
Keep the same rule: registry calls go through your game backend, not the
shipped client.

## Physical ↔ digital bridge

Physical cards carry a QR/NFC encoding a claim code. Scanning (the viewer's
Scan tab) hits `POST /v1/claims`, which links that `card_instances` row to
the player's account and appends a `claim` row to the ledger. The registry
then publishes to the `entitlement-changes` Pub/Sub topic so the digital
games grant entitlements. NFT ownership is validated internally from the
ledger in Phase 1 (there is no chain indexer); the only chain interaction
anywhere is the scheduled proof-anchoring job.

## Workflow: shipping a new card

1. Add `cards/<slug>.yaml` (copy `the-temp.yaml`).
2. Validate: `python -c "import json,yaml,jsonschema; jsonschema.validate(yaml.safe_load(open('cards/<slug>.yaml')), json.load(open('schemas/card-definition.schema.json')))"`
3. Open a PR. CI runs the validation + a dry-run seed.
4. Merge → seed job upserts the new definition version and its
   `game_card_profiles`.
5. Games pick up new profiles on next startup or `ruleset_version` bump.

## What's still to build

- Cloud Functions — scaffolded in `functions/main.py` (all Spark-safe;
  deploy with `firebase deploy --only functions,firestore` against the
  `cardrealm-staging` project in `.firebaserc`). Production is a
  **dedicated registry Firebase project** (decision 2026-10-12; to be
  created, added to `.firebaserc` as the `prod` alias) — the live game
  project is never a deploy target, and games reach the registry only
  through the server-mediated API (see `firestore/data-model.md`,
  "Project topology"):
  `onLedgerWrite`, `onEntitlementWrite` (Pub/Sub publish), `claimCard`,
  `mintAuthToken` (Wix-backend-initiated), `reportStolenOrDestroyed`,
  `linkPlayerId` (app identity link by email — the CARDREALM/Base44
  app's backend calls it to record `players.externalIds`).
  The Python SDK and endpoint contract in this README map 1:1 onto
  callable HTTPS functions — Arena's game server calls those instead of a
  separate FastAPI service.
- Proof anchoring: `.github/workflows/anchor-proofs.yml` (scheduled,
  twice daily) + `scripts/anchor_proofs.py` — the only chain interaction.
- `sdks/web/` — built: `card-realm-client.js` (browser, no secrets),
  `registry-client-node.js` (Node port of the Python SDK), and
  `server-proxy.example.js` (Express router implementing the exact routes the
  browser client expects: profile passthrough, entitlements, ownership,
  authoritative deck validation, moderator-gated proof reports).
  See `sdks/web/README.md` for the route contract.
- Wix Velo: member login → `mintAuthToken` bridge (Wix backend calls us,
  shared secret); `onMemberCreated`/`onMemberUpdated` webhooks → player
  upsert.
- Google Sites embeds + the scheduled AI blogger job (Blogger API —
  allowed on the Spark plan).
