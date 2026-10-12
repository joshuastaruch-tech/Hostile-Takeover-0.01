# Gumroad → Wix verification & account provisioning

**Status:** plan (2026-10-12). Part of Beta 0.01.
**Purpose:** Gumroad is where MYTHOS memberships are sold today; Wix is
the membership website. When Gumroad says someone bought or holds a
membership, Wix and the registry (Firebase) should learn about it
automatically — verified on the backend, with accounts created when they
don't exist. No manual syncing, no member registering twice.

## Design rules (inherited)

- **Spark plan:** registry Cloud Functions never call non-Google APIs.
  Gumroad calls *us* (inbound is fine); outbound verification calls happen
  only where they're allowed.
- The original game and its backend are **not modified**.
- **Idempotent:** the same Gumroad event processed twice changes nothing
  the second time. Gumroad IDs are the dedupe keys.

## Flow (recommended: Wix-mediated, real-time)

1. **Gumroad → Wix.** Gumroad Ping (sales) plus resource subscriptions
   (membership created/cancelled, refund, dispute) point at a Wix backend
   HTTP function on the membership site. The endpoint URL carries a
   secret token — same shared-secret pattern as `WIX_WEBHOOK_SECRET`.
2. **Wix verifies with Gumroad.** Wix backend code can call external
   APIs, so it verifies each event with one Gumroad API call (fetch the
   sale/subscription by ID). A ping is never trusted on its own;
   unverifiable events are dropped and logged.
3. **Wix member: create-or-match.** Match by email. No member → create
   one (Wix Members API) at the tier given by the product→tier map.
   Existing member → update tier/plan. The buyer never signs up
   separately.
4. **Wix → registry.** The same Wix backend calls `mintAuthToken` with
   `purpose: 'sync'` (the bridge is already built). The registry creates
   the Firebase user `wix_<memberId>` and upserts `players/{uid}`. The
   call also carries the tier so the registry writes the matching
   `entitlements` in the same pass (small contract extension — see Open
   decisions).
5. **Games read entitlements** from the registry via the server-mediated
   API, as designed. Beta 0.01 gets this now; the original game gets the
   identical answer after its later patch.

## Reconciliation (safety net — GitHub Actions)

A scheduled Action (same pattern as `anchor-proofs.yml`, twice daily)
pulls Gumroad membership/sales state and diffs it against registry
entitlements:

- refund / chargeback / cancelled-and-expired → revoke the entitlement,
  downgrade the Wix member.
- anything Gumroad doesn't confirm → revoked.

This catches missed pings and forged events. It's a diff, not a re-sync,
so it stays cheap.

## Why this shape (efficiency)

- One webhook receiver, one verification call per event, **zero polling
  on the hot path** — a purchase provisions the Wix and Firebase accounts
  in seconds.
- The only scheduled work is the reconciliation sweep.
- *Alternative considered:* a GitHub Action does everything (verify +
  create accounts). Fewer moving parts in Wix, but provisioning waits
  for the Action's schedule and most polls are no-ops. Kept as fallback
  if Wix HTTP functions prove awkward.

## Events handled

| Gumroad event | Action |
|---|---|
| Sale / membership created | Provision accounts, grant entitlement |
| Membership renewed | Extend entitlement |
| Membership cancelled | Record end date; access until period end, reconciliation revokes after |
| Refund / dispute | Revoke (on ping if subscribed, otherwise at reconciliation) |

## Identity & matching

- Join key: **email** — Gumroad buyer email ↔ Wix member email ↔
  registry `players.email`.
- Registry UID stays `wix_<memberId>`: Wix is the identity hub, Gumroad
  never writes to the registry directly.
- The product→tier map (Gumroad product ID → cultist / operative /
  overlord → entitlement scope) lives in one place: Wix backend config,
  mirrored in `firestore/data-model.md`.

## Failure handling

- Wix function returns non-200 on transient failure → Gumroad retries.
- Every event is logged under its Gumroad ID for audit and dedupe.
- Reconciliation is the backstop for anything the real-time path misses.

## Open decisions

1. **Grant timing:** ✅ implemented per recommendation (2026-10-12) —
   grant immediately after the inline verification at step 2;
   reconciliation is the backstop, not a gate.
2. **Grant mechanism:** ✅ implemented per recommendation (2026-10-12) —
   the `mintAuthToken` sync call carries the tier
   (`syncMemberEntitlement` in the bridge; `_sync_membership` in
   `functions/main.py`). The function also has the `purpose === 'sync'`
   branch: upsert only, no token minted.
3. **The product→tier map itself** — still open: needs the Gumroad
   product list. Placeholders marked `TODO(Joshua)` in
   `wix/backend/gumroad-http-functions.js`,
   `scripts/reconcile_gumroad.py`, and `firestore/data-model.md`.
