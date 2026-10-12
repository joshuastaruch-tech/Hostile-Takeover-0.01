# Odyssey integration contract (Godot / Unity)

> Hand this file to Claude Code verbatim, with the `card-registry` repo
> checked out. Also read `../../README.md` and
> `../../schemas/card-definition.schema.json` first — they are normative.

## Goal

Integrate the game **Odyssey** (Godot 4.x via `HTTPClient`, or Unity via
`UnityWebRequest`) with the Card Registry so that:

1. Deck validation at match start uses the registry as the authority on
   what each card is and whether it's legal in Odyssey.
2. Ownership checks go through the player's **game backend**, never from the
   shipped client directly to the registry.
3. NFT-owned and physically-scanned cards become playable via entitlements.

## Non-negotiable rules

- The registry API key lives on the **game backend only**. The shipped
  Godot/Unity client never holds it and never calls the registry directly.
- The client asks the backend ("can I field instance X?"); the backend asks
  the registry. Never trust the client on ownership.
- Card **definitions** are canonical and versioned. Per-game numbers come
  from `game_card_profiles`, not from hardcoded values in game code.
- Cache profiles keyed by `(definition_slug, ruleset_version)`. When the
  registry reports a new `ruleset_version` for `odyssey`, drop the cache.

## Connection

- Base URL: `https://registry.cardrealm.example` (env-configurable)
- Auth: `Authorization: Bearer <API_KEY>` on backend-to-registry calls.

## Endpoints you need

| Method | Path | Use |
|---|---|---|
| GET | `/v1/cards/{slug}/games/odyssey` | Cost/power/legality for Odyssey |
| GET | `/v1/players/{pid}/ownership/{iid}` | 200 = owns, 404 = doesn't |
| GET | `/v1/players/{id}/entitlements?game=odyssey` | All cards playable by this player |
| POST | `/v1/claims` | Redeem a physical QR/NFC claim code |
| POST | `/v1/proofs` | Report stolen/destroyed → anchors proof hash on-chain |

## Example payloads

`GET /v1/cards/the-temp/games/odyssey` →

```json
{
  "slug": "the-temp",
  "game": "odyssey",
  "ruleset_version": "1.0.0",
  "cost": null,
  "power": null,
  "toughness": null,
  "is_legal": false,
  "banned_reason": "Devour mechanic not implemented in Odyssey ruleset v1",
  "rules_patch": null
}
```

`GET /v1/players/{id}/entitlements?game=odyssey` →

```json
{
  "player_id": "uuid…",
  "game": "odyssey",
  "entitlements": [
    { "instance_id": "uuid…", "definition_slug": "the-temp",
      "serial": "000/000", "granted_at": "2026-10-10T06:00:00Z",
      "revoked_at": null }
  ]
}
```

## Flows to implement

### A. Deck validation (match start, backend)

1. Client sends deck list of `instance_id`s.
2. Backend: for each, `GET /v1/cards/{slug}/games/odyssey` → reject if
   `is_legal == false`; use returned cost/power, not client values.
3. Backend: `GET /v1/players/{pid}/ownership/{iid}` per instance → reject
   on 404.
4. Only then start the match.

### B. Granting a card (purchase / earn / event)

Backend calls `POST /v1/transfers` (or the entitlement grant endpoint the
API exposes), then pushes the updated entitlement list to the client.
Client treats entitlements as display data, never as proof.

### C. NFT ownership → playable (Phase 1: internal validation)

1. Backend calls the registry `owns(playerId, instanceId)` check, which
   validates against the internal ledger: not the owner → reject;
   `destroyed` → reject; `stolen` → allow with a warning your game
   surfaces (freeze trading, flag the deck, etc.).
2. On success, backend grants the Odyssey entitlement for the instance.
3. No wallet connection, no signature challenge — those arrive in Phase 2.
   The only blockchain interaction in the whole system is the stolen /
   destroyed proof anchoring described in `firestore/data-model.md`.

### D. Physical scan → claim

1. Client scans QR/NFC → sends claim code to backend (never the raw
   `claim_code_hash`).
2. Backend `POST /v1/claims` → on success, instance is ledger-linked to
   the player and an Odyssey entitlement is granted.

## Godot specifics

- Use `HTTPClient` (or `HTTPRequest` nodes) with JSON bodies; parse with
  `JSON.parse_string`.
- Put registry access behind an autoload (e.g. `RegistryService`) that talks
  to **your backend**, with methods like `validate_deck(instance_ids)` and
  `get_entitlements()`. No API keys in project settings or exports.

## Unity specifics

- Use `UnityWebRequest` with coroutines/`async` + `JsonUtility` or
  Newtonsoft.Json. Same layering: a `RegistryService` MonoBehaviour that
  calls your backend.

## Definition of done

- [ ] Deck validation rejects illegal/unowned cards using live registry data
- [ ] No API key or registry URL hardcoded in shipped client
- [ ] Entitlement changes (grant/revoke) reflect in-game without a restart
- [ ] `the-temp` is correctly rejected in Odyssey (banned) while remaining
      playable data-wise for Arena/MYTHOS profiles
