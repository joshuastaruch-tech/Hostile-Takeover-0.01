# Wix Velo bridge — member login → Firebase custom token

Local prep only: nothing here is pasted into the live Wix site yet,
and nothing is deployed. These files are what you (or Dexter, in a
browser session you sign into) paste into the Wix editor's Dev Mode
when you're ready. The live MYTHOS backend and the live Wix site are
untouched.

## Files

| File | Paste into | Role |
|---|---|---|
| `backend/cardrealm-auth.jsw` | Dev Mode → Backend | Verifies the member natively, calls `mint_auth_token` with the shared secret, returns the custom token. Also exports `syncMember` and `syncMemberEntitlement` for the webhook handlers and the Gumroad pipeline. |
| `backend/events.js` | Dev Mode → Backend | `onMemberCreated` / `onMemberUpdated` → player upsert. **Draft — enable after one staging test in Dev Mode.** |
| `backend/gumroad-http-functions.js` | Dev Mode → Backend (as `http-functions.js`) | Gumroad Ping endpoint: verifies the sale with the Gumroad API, creates/matches the Wix member, syncs the entitlement to the registry. |
| `frontend/firebase-signin.js` | Member page code | Gets the token from the backend and `signInWithCustomToken` into Firebase (staging config). |

## Setup checklist (staging)

1. Generate one shared secret value (any long random string).
2. Wix: Secrets Manager → add it as `WIX_WEBHOOK_SECRET`.
3. Firebase (`cardrealm-staging` only): Secret Manager → add the
   same value as `WIX_WEBHOOK_SECRET`. The function reads it via
   `_secret("WIX_WEBHOOK_SECRET")` in `functions/main.py`.
4. Deploy functions to staging, then confirm the deployed
   `mint_auth_token` URL matches `MINT_URL` in
   `backend/cardrealm-auth.jsw`.
5. Firebase console → `cardrealm-staging` → register a Web app,
   paste its config into `frontend/firebase-signin.js`.
6. Paste the three files into Dev Mode, log in as a member, and
   confirm a `players/wix_<memberId>` doc appears in staging
   Firestore.

## Sync branch (resolved 2026-10-12)

`mint_auth_token` now branches on `purpose`: `login` (default) upserts
the player and mints a token; `sync` upserts only — no token minted.
Sync calls may also carry `tier` / `gameSlugs` / `sourceEventId` /
`revoke`, in which case the function grants or revokes the per-game
membership entitlements (deterministic IDs, idempotent) and logs the
event under `gumroadEvents/{gumroadId}`.

## Gumroad pipeline setup (staging)

In addition to the checklist above:

1. Wix Secrets Manager: add `GUMROAD_PING_SECRET` (any long random
   string), `GUMROAD_ACCESS_TOKEN` (from Gumroad → Settings →
   Advanced → API), `WIX_API_KEY`, and `WIX_SITE_ID`.
2. Fill `PRODUCT_TIER_MAP` in `backend/gumroad-http-functions.js`
   with the real Gumroad product IDs (same map lives in
   `scripts/reconcile_gumroad.py` and `firestore/data-model.md`).
3. Paste `backend/gumroad-http-functions.js` as
   `backend/http-functions.js`, publish the staging site, and set the
   Gumroad Ping URL to
   `https://<staging-site>/_functions/gumroadPing?key=<GUMROAD_PING_SECRET>`.
4. GitHub repo secret `GUMROAD_ACCESS_TOKEN` (same token) for the
   reconciliation Action (`.github/workflows/gumroad-reconcile.yml`).
5. Test with a real low-price Gumroad purchase: member created on
   Wix, `players/wix_<id>` + `entitlements/membership_...` docs in
   staging Firestore, refund → entitlement revoked.

## Still separate from this bridge

Before a first staging deploy, also outstanding (from README):
- Create the Pub/Sub topic once:
  `gcloud pubsub topics create entitlement-changes`
- GitHub repo secrets for the anchoring Action:
  `FIREBASE_SERVICE_ACCOUNT`, `CHAIN_RPC_URL`, `ANCHOR_PRIVATE_KEY`
