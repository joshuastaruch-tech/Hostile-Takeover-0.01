# Web SDK — MYTHOS (HTML5)

Three files, one trust boundary:

```
browser (card-realm-client.js)  →  YOUR MYTHOS server (server-proxy.example.js)  →  registry (registry-client-node.js)
        no secrets, session cookie only         API key lives here, player id from session        Firestore / API
```

**The browser never talks to the registry.** It talks to your game server,
your game server talks to the registry with the API key — the same rule as
Arena. Copy these files into your MYTHOS repo; no build step, no dependencies
(plain ES modules, Node 18+ on the server, any modern browser).

## Files

| File | Runs on | Purpose |
|---|---|---|
| `card-realm-client.js` | browser | `CardRealmClient` — profiles, entitlements, ownership questions, deck validation, proof reports. Thin, no secrets. |
| `registry-client-node.js` | your server | `CardRegistry` — Node port of `sdks/python/card_registry.py`, method-for-method. Reads `CARD_REGISTRY_URL` / `CARD_REGISTRY_API_KEY`. |
| `server-proxy.example.js` | your server | Express router implementing the exact routes the browser client expects. Copy handlers into your real server. |

## The route contract your server must expose

| Browser call | Route | Server does |
|---|---|---|
| `client.card(slug)` | `GET /api/registry/cards/:slug?version=` | `reg.card()` passthrough |
| `client.profile(slug)` | `GET /api/registry/cards/:slug/profile?game=mythos` | `reg.profile()` (cached) |
| `client.entitlements()` | `GET /api/registry/entitlements?game=mythos` | `reg.entitlements(playerFromSession)` |
| `client.owns(iid)` | `GET /api/registry/ownership/:iid` → `{ owns }` | `reg.owns(playerFromSession, iid)` |
| `client.validateDeck(ids)` | `POST /api/registry/decks/validate` → `{ valid, fielded, errors, warnings }` | owns + legality per instance (authoritative) |
| `client.reportProof(...)` | `POST /api/registry/proofs` (moderator-gated) | `reg.reportProof()` |

Error codes from deck validation: `not_owned`, `destroyed`, `unknown_definition`,
`not_legal` (with `detail` = ban reason), `profile_unavailable`; warnings: `stolen_warning`.

## Browser usage

```html
<script type="module">
  import { CardRealmClient } from "./card-realm-client.js";
  const cards = new CardRealmClient({ gameSlug: "mythos" }); // same-origin server

  // Render a card (UX hint only — not authoritative)
  const profile = await cards.profile("the-temp");
  if (cards.fieldable(profile)) showCard(profile);

  // Validate at deck save AND at match start
  const { valid, errors, warnings } = await cards.validateDeck(deckInstanceIds);
  if (!valid) showDeckErrors(errors);
  if (warnings.length) showStolenFlags(warnings);
</script>
```

`fieldable()` is a UX convenience. The server re-validates — always.

## Server wiring

```js
import express from "express";
import { registryRouter } from "./server-proxy.example.js";

const app = express();
// mount BEFORE your static files; plug in your session middleware first
app.use(registryRouter());
```

Then implement the two hooks marked in the example: `getPlayerId(req)`
(session → registry player id) and `requireModerator` (role check for
`reportProof`). Profiles are cached in-memory per `(slug, game)`; when the
registry bumps `games/mythos.rulesetVersion`, call `reg.invalidateProfiles()`.

## Phase 1 NFT note

No wallet code here, by design. NFT ownership is validated internally from
the registry ledger (`currentOwnerId` + `status` on the instance) — the
server's `owns()` check already covers NFT instances. Wallet signatures
arrive in Phase 2 and land in `registry-client-node.js` only, never in the
browser bundle.
