# Firestore data model

Physical mapping of the Card Registry onto Firebase. The SQL migration
(`migrations/001_initial_schema.sql`) remains the **logical model** — this
file is what you actually deploy.

Conventions: `{...}` = document ID. `→` = reference (stored as document
path string or `DocumentReference`).

## Project topology

**Decision 2026-10-12:** the registry database lives in its **own dedicated
Firebase project** — never the MYTHOS game project. Registry deploys cannot
touch the live game backend, by construction rather than by procedure.

- **Staging:** `cardrealm-staging` (the `.firebaserc` default) — all
  development and testing happens here.
- **Production:** a dedicated registry project, to be created; its ID gets
  added to `.firebaserc` as the `prod` alias when it exists.

Consequences, by design:

- Firebase Auth is per-project, so game clients **never** read registry
  Firestore directly. All game access is server-mediated: the game server
  calls the registry API with the Node SDK
  (`sdks/web/registry-client-node.js`, `CARD_REGISTRY_URL` /
  `CARD_REGISTRY_API_KEY`); browser clients talk only to their own game
  server's `/api/registry/*` routes (see `sdks/web/server-proxy.example.js`).
  This is how the web SDK was already built — no rework needed.
- Registry identity is anchored on the **Wix member**: `mintAuthToken`
  creates registry users with uid `wix_<memberId>`. Each game's own player
  ID is linked on the `players` doc via `externalIds` so ownership and
  entitlements resolve across projects.
- Entitlement fan-out still works cross-project: the `entitlement-changes`
  Pub/Sub topic lives in the registry project, and Pub/Sub itself delivers
  to subscribers — no Cloud Function calls out (Spark-safe).

## Collections

### `issuers/{issuerId}`
| Field | Type | Notes |
|---|---|---|
| name | string | e.g. `CARDREALM` |
| slug | string | e.g. `cardrealm` |

### `players/{uid}` — UID = Firebase Auth UID
| Field | Type | Notes |
|---|---|---|
| displayName | string? | |
| email | string? | |
| wixMemberId | string? | link to Wix Members Area |
| externalIds | map? | per-game/app player IDs, e.g. `{ mythos: <game-project uid>, base44: <CR- player ID> }` — set via `link_player_id` (email join) |
| createdAt | timestamp | |

> **Phase 2 (deferred):** on-chain wallets. The subcollection
> `players/{uid}/wallets/{walletId}` (`{ chain, address, verifiedAt? }`) is
> reserved for later. Until then, NFT ownership is validated **internally**
> from the ledger (see below) — no wallet connection, no signature
> challenges.

### `cardDefinitions/{slug}__v{version}` — e.g. `the-temp__v1`
| Field | Type | Notes |
|---|---|---|
| slug, name, typeLine, rulesText | string | |
| flavorText | string? | ARG fragments — the AI blogger reads this |
| cost | number? | null = variable |
| rarity | string | `common|uncommon|rare|mythic|legendary|secret` (legendary added 2026-10-12 to match Base44) |
| serialScheme | string | `numbered|null|open` |
| version | number | errata → new doc, never overwrite |
| supersedes | string? | e.g. `the-temp__v1` |
| issuerRef | reference → `issuers/{id}` | |
| metadata | map | |
| createdAt | timestamp | |

Subcollection `cardDefinitions/{id}/media/{kind}` — doc ID is the kind
(`art`, `model_3d`, `audio`, `video`): `{ url, mimeType? }`. Missing doc =
empty slot in the viewer.

Subcollection `cardDefinitions/{id}/gameProfiles/{gameSlug}` — the
multi-game hinge (was `game_card_profiles`):
`{ costOverride?, power?, toughness?, stats?, isLegal=true, bannedReason?,
rulesPatch?, metadata }`.
`stats` is a map of game-specific numbers — e.g. MYTHOS uses
`{ control, sanity, power, flesh, leash, upkeep }`. Doc ID is the game slug
(`mythos`, `arena`, `odyssey`), so one collectionGroup query pulls every
profile for a game.

### `cardInstances/{instanceId}` (auto-ID)
| Field | Type | Notes |
|---|---|---|
| definitionRef | reference → `cardDefinitions/{id}` | |
| serial | string? | `000/000`, `042/500`, null for open |
| edition | string | default `first` |
| condition | string? | physical only |
| claimCodeHash | string? | hashed QR/NFC claim secret |
| **currentOwnerId** | string? | **denormalized** — maintained by function (replaces the SQL view) |
| status | string | `active|stolen|destroyed` — default `active`; gates ownership validation |
| createdAt | timestamp | |

Subcollection `cardInstances/{id}/ledger/{ledgerId}` (auto-ID, **append-only**):
`{ fromPlayerId?, toPlayerId?, transferType, txRef?, createdAt }`.
`transferType ∈ mint|burn|sale|trade|claim|bridge`.

### `games/{gameSlug}` — e.g. `arena`, `mythos`, `odyssey`
`{ name, platform, rulesetVersion }`. Bump `rulesetVersion` → games drop
their profile caches.

### `entitlements/{entitlementId}` (auto-ID)
`{ playerId, instanceId, gameSlug, grantedAt, revokedAt? }`.
Composite indexes: `(playerId, gameSlug)`, `(gameSlug, grantedAt)`.

Membership entitlements (Gumroad → Wix pipeline) are the exception to
auto-ID: deterministic doc ID `membership_{uid}_{gameSlug}`,
`instanceId: null`, plus `tier` and `source: 'membership'` — so sync
events and the reconciliation sweep grant/revoke idempotently.

### `gumroadEvents/{gumroadId}`
Audit/dedupe log written by `mint_auth_token` sync calls:
`{ playerId, tier, revoke, receivedAt }`.

### Gumroad product → tier map
| Gumroad product ID | Tier | Games |
|---|---|---|
| _(TBD — fill from the Gumroad product list)_ | cultist / operative / overlord | mythos |

Mirrored in `wix/backend/gumroad-http-functions.js` and
`scripts/reconcile_gumroad.py`; keep all three in step.

### `nftTokens/{chain}_{contract}_{tokenId}`
`{ instanceId, chain, contractAddress, tokenId, tokenUri? }`.
**Ownership is validated internally**: the owner of the linked
`cardInstances/{id}` (via `currentOwnerId` + `status`) *is* the NFT owner.
No wallet signature required. The chain fields are descriptive metadata for
now; transfer sync from chain events arrives in Phase 2 with wallets.

### `physicalLinks/{linkId}` (auto-ID)
`{ instanceId, nfcUid?, qrPayload? }` — `qrPayload`/`nfcUid` unique in practice
(enforced by the claim function, which checks before linking).

### `proofs/{proofId}` (auto-ID) — stolen / destroyed attestations
`{ instanceId, proofType, evidenceRefs[]?, evidenceHash, chain?, txHash?,
status, reporterPlayerId, createdAt, anchoredAt?, error? }`.
- `proofType ∈ stolen|destroyed`
- `evidenceHash` = SHA-256 of the canonical proof JSON (instance, serial,
  definition slug, reporter, timestamp, evidence refs)
- `status ∈ pending|anchored|failed`
- The **only** blockchain interaction in the system is anchoring this hash.

## Internal NFT ownership validation

No wallets, no signatures — one check, run on the backend:

```
function validateOwnership(playerId, instanceId):
  inst = get(cardInstances/{instanceId})
  if inst.status == 'destroyed': return { ok: false, reason: 'destroyed' }
  if inst.currentOwnerId != playerId: return { ok: false, reason: 'not-owner' }
  if inst.status == 'stolen':
    return { ok: true, warning: 'reported stolen — proof anchored' }
  return { ok: true }
```

- `owns()` in the SDKs implements exactly this.
- Games decide how to handle the `stolen` warning (freeze trading, flag the
  deck, etc.). Destroyed cards are never playable or transferable.
- The blockchain never answers "who owns this" — it only notarizes *that a
  theft/destruction was reported, when, and by whom*.

## Denormalization & triggers (Cloud Functions)

> **Spark-plan design.** Everything below is written for Firebase's free
> Spark plan. The one hard rule: Cloud Functions on Spark cannot call
> non-Google APIs. Two patterns handle it: **(a)** flip the direction —
> have external services (Wix) call *us* instead of us calling them;
> **(b)** move non-Google outbound work (chain anchoring) into a
> scheduled GitHub Action. Upgrading to Blaze later is a billing toggle,
> not a re-architecture.

1. **`onLedgerWrite`** — trigger on create of
   `cardInstances/{id}/ledger/{lid}` → transactionally set
   `cardInstances/{id}.currentOwnerId = toPlayerId`. This is the Firestore
   replacement for the `current_ownership` SQL view.
2. **`onEntitlementWrite`** — on create/update of `entitlements/{id}` →
   publish to Pub/Sub topic `entitlement-changes` (Google-internal, so
   Spark-safe). Game backends subscribe via push subscription from their
   own project (Pub/Sub delivers cross-project), or poll `GET /v1/players/{id}/entitlements?game={slug}`.
   *Why not call game webhooks from the function?* Spark blocks Cloud
   Functions from calling non-Google endpoints — Pub/Sub is the
   free-plan-safe fan-out.
3. **`claimCard`** (callable) — input `{ claimCode, gameSlug }`:
   hash the code, find the instance by `claimCodeHash`, verify it has no
   owner yet, then in one transaction write the `claim` ledger row and the
   entitlement. Rate-limit per user.
4. **`mintAuthToken`** (https, **Wix-backend-only**) — the direction is
   flipped so no outbound call ever leaves Firebase: Wix's backend calls
   *us*.
   - Wix Velo backend code verifies the member natively
     (`wix-members-backend`), then calls this endpoint with
     `{ wixMemberId }` plus the shared secret (`WIX_WEBHOOK_SECRET`,
     kept in Secret Manager — a Google API, allowed on Spark).
   - The function creates the Firebase user if needed (Admin SDK),
     upserts `players/{uid}` with `wixMemberId`, mints a Firebase
     **custom token**, and returns it to Wix's backend.
   - Wix passes the token to its frontend, which signs into Firebase —
     one login across the Wix site, the viewer, and the games.
   - The same endpoint also serves Wix webhooks (`onMemberCreated`,
     `onMemberUpdated`) so `players/{uid}` stays in sync.
5. **`reportStolenOrDestroyed`** (callable) — input
   `{ instanceId, proofType, evidenceRefs[] }`: verifies the caller owns the
   instance (or is the issuer), sets `status` (`stolen`|`destroyed`), writes
   a `proofs/{id}` row with `status: pending`, and for `destroyed` also
   appends a `burn` ledger row.
6. **Proof anchoring → GitHub Action, not a Cloud Function.**
   Submitting a chain transaction needs an outbound call to a non-Google
   RPC endpoint, which Spark blocks inside functions — so anchoring runs
   as a scheduled workflow: `.github/workflows/anchor-proofs.yml` (cron:
   twice daily, plus a manual `workflow_dispatch` button). Each run
   (implementation: `scripts/anchor_proofs.py`):
   - Queries `proofs` where `status == 'pending'` (Firebase Admin SDK;
     the service-account key lives as a GitHub secret).
   - Builds the canonical proof JSON, SHA-256 hashes it into
     `evidenceHash`, submits one transaction carrying the hash
     (`CHAIN_RPC_URL` — a free Alchemy/Infura endpoint; a memo tx on an
     EVM chain labelled `PROOF_CHAIN`), then marks the proof `anchored`
     with `txHash`/`anchoredAt` (or `failed` with an error).
   - Batching means a proof anchors within ~12h of the report instead of
     instantly — fine at this stage, and it keeps the bill at $0.
   **This remains the system's only blockchain interaction.**

## Wix wiring

- Wix Members Area is the membership system of record, and Wix's
  backend is the authority on its own members — so it initiates
  everything. Velo backend code calls `mintAuthToken` (shared secret) at
  member login to fetch a Firebase custom token, and Wix webhooks
  (`onMemberCreated`, `onMemberUpdated`) hit the same endpoint to keep
  `players/{uid}` in sync. Nothing on Firebase's side ever calls out to
  Wix, which is what keeps the design Spark-safe.
- Never store the Firebase Admin key in Velo frontend code — all registry
  writes go through Cloud Functions with the Admin SDK.

## Google Sites + AI blogger

- **Viewer embeds**: Google Sites → Insert → Embed → paste viewer card URLs
  (`omni-card-view…/card/{id}`). Card pages are deep-linkable, so each blog
  post can embed its card.
- **Blogger job** (scheduled function): queries `cardDefinitions` ordered by
  `createdAt`, pulls new/updated `flavorText` + `rulesText`, and drafts
  Blogger posts (lore drops, ARG fragments, new-card announcements).
  Published lore can flow back as new card-definition versions.
  Blogger is a Google API and Cloud Scheduler's free tier covers the cron —
  both run fine on the Spark plan.
