# Staging deploy — ordered checklist

Everything here targets the separate `cardrealm-staging` Firebase project
(`.firebaserc` default) and a local branch of this repo. Nothing in this
list deploys to, pastes into, or changes the live MYTHOS game, its
backend, or the live Wix site until Step 6 — and Step 6 is done by
Joshua (or in a Wix editor session he signs into), never unattended.

This file consolidates prerequisites that were previously scattered
across `README.md`, `wix/README.md`, and
`.github/workflows/anchor-proofs.yml`. It adds no new design decisions.

**Sequence update (Joshua, 2026-10-12):** work order is Firebase
deploy first, then the Wix rebuild (rework of the existing site in
place), then sign-in integration. So Steps 1–5, 7, 8 are the deploy
phase; Step 6 (the Wix paste) belongs to the later sign-in phase,
after the rebuild — it is kept here for completeness, marked as such.

## Step 0 — DECIDED and built (2026-10-12)

`mint_auth_token` in `functions/main.py` branches on `purpose`:
`'login'` (default) upserts the player and mints a token; `'sync'`
upserts only — no token minted. Sync calls also drive membership
tier grants/revokes (`_sync_membership`). Verified by
`tests/test_registry_functions.py` (35/35 checks pass). Nothing to
decide here anymore.

## Step 1 — Pub/Sub topic (once)

`on_entitlement_write` publishes to a topic that must exist first:

- [ ] `gcloud pubsub topics create entitlement-changes`
      (run against the `cardrealm-staging` project)

## Step 2 — Shared Wix secret (same value in two places)

- [ ] Generate one long random string.
- [ ] Wix: Secrets Manager → add as `WIX_WEBHOOK_SECRET`.
- [ ] Firebase (`cardrealm-staging` only): Secret Manager → add the
      same value as `WIX_WEBHOOK_SECRET`.
      The function reads it via `_secret("WIX_WEBHOOK_SECRET")` in
      `functions/main.py`; the bridge reads its copy via
      `getSecret('WIX_WEBHOOK_SECRET')`. A mismatch = every login 403s.

## Step 3 — Deploy functions + Firestore rules to staging

- [ ] `firebase deploy --only functions,firestore`
      (`.firebaserc` already points at `cardrealm-staging`. Do not
      deploy these rules over the live game project's rules.)

## Step 4 — Confirm the mint endpoint URL

- [ ] After Step 3, confirm the deployed URL matches `MINT_URL` in
      `wix/backend/cardrealm-auth.jsw`:
      `https://us-central1-cardrealm-staging.cloudfunctions.net/mint_auth_token`

## Step 5 — Firebase web app config for the sign-in snippet

- [ ] Firebase console → `cardrealm-staging` → register a Web app.
- [ ] Paste its config into `wix/frontend/firebase-signin.js`.

## Step 6 — Paste the Wix bridge (SIGN-IN PHASE — after the Wix rebuild, per the 2026-10-12 order)

- [ ] Dev Mode → Backend: `wix/backend/cardrealm-auth.jsw`
- [ ] Dev Mode → Backend: `wix/backend/events.js` (draft)
- [ ] Member page code: `wix/frontend/firebase-signin.js`
- [ ] Log in as a member and confirm a `players/wix_<memberId>` doc
      appears in staging Firestore.

## Step 7 — GitHub secrets for the anchoring Action

Repo Settings → Secrets and variables → Actions
(`.github/workflows/anchor-proofs.yml`, runs 06:00 + 18:00 UTC,
plus manual dispatch):

- [ ] `FIREBASE_SERVICE_ACCOUNT` — service-account JSON with Firestore
      read/write on `proofs` and `cardInstances`.
- [ ] `CHAIN_RPC_URL` — HTTPS chain endpoint.
- [ ] `ANCHOR_PRIVATE_KEY` — funded keypair; one memo tx per proof.
- [ ] Optional variable: `PROOF_CHAIN` — label stored on the proof row
      (workflow example: `base-sepolia`).

## Step 8 — Testnet dry run before trusting the schedule

- [ ] With Step 7 secrets set to testnet values, use the workflow's
      manual "Run workflow" dispatch once and confirm a pending proof
      is marked anchored (not failed) before relying on the twice-daily
      schedule. The nonce/`from` signing bug in
      `scripts/anchor_proofs.py` is already fixed and verified locally;
      this run proves the secrets + RPC wiring, not the code path.

## After staging works

Only then is there anything to discuss about the live projects — and
that is a separate decision, not part of this checklist.
