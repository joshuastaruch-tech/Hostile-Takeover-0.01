"""Card Registry — Cloud Functions (Python 3.12, 2nd gen).

Spark-plan design: nothing here calls a non-Google API.
  - Firestore triggers, Pub/Sub, and Secret Manager are Google-internal.
  - Wix initiates auth (we never call out to Wix).
  - Chain anchoring lives in .github/workflows/anchor-proofs.yml.

Deploy:   firebase deploy --only functions,firestore
Emulate:  firebase emulators:start
"""

from __future__ import annotations

import hashlib
import json
import os

from firebase_functions import firestore_fn, https_fn, options
from firebase_admin import auth, firestore, initialize_app
from google.cloud import pubsub_v1, secretmanager

initialize_app()

options.set_global_options(region="us-central1", max_instances=10)

db = firestore.client()
_secrets = secretmanager.SecretManagerServiceClient()
_publisher = pubsub_v1.PublisherClient()


def _project() -> str:
    return os.environ.get("GCLOUD_PROJECT", "")


def _secret(name: str) -> str:
    path = f"projects/{_project()}/secrets/{name}/versions/latest"
    return _secrets.access_secret_version(
        request={"name": path}).payload.data.decode()


def _auth_parts(auth_obj):
    """Callable auth shape differs across SDK versions; handle both."""
    if auth_obj is None:
        return None, {}
    if isinstance(auth_obj, dict):
        return auth_obj.get("uid"), auth_obj.get("token") or {}
    return getattr(auth_obj, "uid", None), getattr(auth_obj, "token", None) or {}


# ---------------------------------------------------------------------------
# Internal NFT ownership validation — single source of truth for owns().
# ---------------------------------------------------------------------------

def validate_ownership(player_id: str, instance_id: str) -> dict:
    snap = db.collection("cardInstances").document(instance_id).get()
    if not snap.exists:
        return {"ok": False, "reason": "not-found"}
    inst = snap.to_dict()
    if inst.get("status") == "destroyed":
        return {"ok": False, "reason": "destroyed"}
    if inst.get("currentOwnerId") != player_id:
        return {"ok": False, "reason": "not-owner"}
    if inst.get("status") == "stolen":
        return {"ok": True, "warning": "reported-stolen"}
    return {"ok": True}


# ---------------------------------------------------------------------------
# 1. Ledger -> currentOwnerId mirror (replaces the SQL current_ownership view)
# ---------------------------------------------------------------------------

@firestore_fn.on_document_created(
    document="cardInstances/{instanceId}/ledger/{ledgerId}"
)
def on_ledger_write(
    event: firestore_fn.Event[firestore_fn.DocumentSnapshot],
) -> None:
    data = event.data.to_dict() or {}
    inst_ref = db.collection("cardInstances").document(event.params["instanceId"])

    @firestore.transactional
    def _tx(t):
        # toPlayerId=None on burn clears the owner.
        t.update(inst_ref, {"currentOwnerId": data.get("toPlayerId")})

    _tx(db.transaction())


# ---------------------------------------------------------------------------
# 2. Entitlement fan-out via Pub/Sub (Spark-safe: no non-Google outbound)
# ---------------------------------------------------------------------------

@firestore_fn.on_document_written(document="entitlements/{entitlementId}")
def on_entitlement_write(
    event: firestore_fn.Event[
        firestore_fn.Change[firestore_fn.DocumentSnapshot]
    ],
) -> None:
    eid = event.params["entitlementId"]
    after = event.data.after
    if after is None or not after.exists:
        payload = {"type": "revoked", "entitlementId": eid}
    else:
        d = after.to_dict()
        payload = {
            "type": "entitlement",
            "entitlementId": eid,
            "playerId": d.get("playerId"),
            "instanceId": d.get("instanceId"),
            "gameSlug": d.get("gameSlug"),
            "tier": d.get("tier"),
            "revoked": d.get("revokedAt") is not None,
        }
    # NOTE: create the topic once: gcloud pubsub topics create entitlement-changes
    topic = _publisher.topic_path(_project(), "entitlement-changes")
    _publisher.publish(topic, json.dumps(payload).encode("utf-8")).result()


# ---------------------------------------------------------------------------
# 3. Physical claim: QR/NFC code -> ledger row + entitlement (one transaction)
# ---------------------------------------------------------------------------

@https_fn.on_call()
def claim_card(req: https_fn.CallableRequest) -> dict:
    # TODO: per-user rate limiting (counter doc or App Check enforcement).
    uid, _ = _auth_parts(req.auth)
    if uid is None:
        raise https_fn.HttpsError("unauthenticated", "Sign in first.")
    data = req.data or {}
    code, game = data.get("claimCode", ""), data.get("gameSlug", "")
    if not code or not game:
        raise https_fn.HttpsError(
            "invalid-argument", "claimCode and gameSlug required.")

    digest = hashlib.sha256(code.encode()).hexdigest()
    matches = list(
        db.collection("cardInstances")
        .where("claimCodeHash", "==", digest).limit(1).stream()
    )
    if not matches:
        raise https_fn.HttpsError("not-found", "Unknown claim code.")
    inst_ref = matches[0].reference
    ent_ref = db.collection("entitlements").document()

    @firestore.transactional
    def _tx(t):
        snap = inst_ref.get(transaction=t)
        if snap.get("currentOwnerId"):
            raise https_fn.HttpsError("already-exists", "Card already claimed.")
        if snap.get("status") == "destroyed":
            raise https_fn.HttpsError("failed-precondition", "Card destroyed.")
        t.set(inst_ref.collection("ledger").document(), {
            "fromPlayerId": None,
            "toPlayerId": uid,
            "transferType": "claim",
            "createdAt": firestore.SERVER_TIMESTAMP,
        })
        t.set(ent_ref, {
            "playerId": uid,
            "instanceId": inst_ref.id,
            "gameSlug": game,
            "grantedAt": firestore.SERVER_TIMESTAMP,
        })

    _tx(db.transaction())
    # on_ledger_write mirrors currentOwnerId from the claim row.
    return {"ok": True, "instanceId": inst_ref.id}


# ---------------------------------------------------------------------------
# 4. Wix-backend-initiated auth bridge (Wix verifies, we mint the token)
#    purpose='login' (default): upsert player + mint a custom token.
#    purpose='sync': upsert only — no credential minted for an event
#    nobody logs in with. Sync calls may also carry a membership tier
#    (from the Gumroad -> Wix pipeline, design/gumroad-wix-verification.md),
#    which grants/revokes per-game membership entitlements idempotently.
# ---------------------------------------------------------------------------

def _sync_membership(uid: str, body: dict) -> list:
    """Apply a membership tier carried by a sync call.

    Entitlement docs use deterministic IDs (membership_{uid}_{gameSlug})
    so re-processing the same event changes nothing. Returns the list of
    game slugs granted (empty on revoke or when no tier was carried).
    """
    tier = body.get("tier")
    if body.get("sourceEventId"):
        # Audit/dedupe log for Gumroad-driven syncs, keyed by Gumroad ID.
        db.collection("gumroadEvents").document(
            str(body["sourceEventId"])).set({
                "playerId": uid,
                "tier": tier,
                "revoke": bool(body.get("revoke")),
                "receivedAt": firestore.SERVER_TIMESTAMP,
            }, merge=True)
    if not tier:
        return []
    granted = []
    for game in body.get("gameSlugs") or ["mythos"]:
        ref = db.collection("entitlements").document(
            f"membership_{uid}_{game}")
        if body.get("revoke"):
            ref.set({"revokedAt": firestore.SERVER_TIMESTAMP}, merge=True)
        else:
            data = {
                "playerId": uid,
                "instanceId": None,
                "gameSlug": game,
                "tier": tier,
                "source": "membership",
                "revokedAt": None,
            }
            if not ref.get().exists:
                data["grantedAt"] = firestore.SERVER_TIMESTAMP
            ref.set(data, merge=True)
            granted.append(game)
    return granted


@https_fn.on_request()
def mint_auth_token(req: https_fn.Request) -> https_fn.Response:
    if req.method != "POST":
        return https_fn.Response("POST only", status=405)
    try:
        secret = _secret("WIX_WEBHOOK_SECRET")
    except Exception:
        return https_fn.Response("server misconfigured", status=500)
    if req.headers.get("X-Webhook-Secret") != secret:
        return https_fn.Response("forbidden", status=403)

    body = req.get_json(silent=True) or {}
    wix_id = body.get("wixMemberId")
    if not wix_id:
        return https_fn.Response("wixMemberId required", status=400)
    purpose = body.get("purpose", "login")

    uid = "wix_" + "".join(c for c in str(wix_id) if c.isalnum())[:100]
    # Email is the ecosystem join key: normalize it, and never let a
    # partial sync (one that omits email/displayName) clobber the
    # stored values with nulls.
    email = (body.get("email") or "").strip().lower() or None
    try:
        auth.get_user(uid)
    except auth.UserNotFoundError:
        auth.create_user(uid=uid, email=email,
                         display_name=body.get("displayName"))
    player = {"wixMemberId": str(wix_id)}
    if email:
        player["email"] = email
    if body.get("displayName"):
        player["displayName"] = body.get("displayName")
    db.collection("players").document(uid).set(player, merge=True)

    if purpose == "sync":
        granted = _sync_membership(uid, body)
        return https_fn.Response(
            json.dumps({"ok": True, "uid": uid, "granted": granted}),
            mimetype="application/json")

    token = auth.create_custom_token(uid).decode()
    return https_fn.Response(json.dumps({"token": token}),
                             mimetype="application/json")


# ---------------------------------------------------------------------------
# 5. Stolen/destroyed report -> status flip + pending proof (Action anchors)
# ---------------------------------------------------------------------------

@https_fn.on_call()
def report_proof(req: https_fn.CallableRequest) -> dict:
    uid, token = _auth_parts(req.auth)
    if uid is None:
        raise https_fn.HttpsError("unauthenticated", "Sign in first.")
    data = req.data or {}
    iid, ptype = data.get("instanceId"), data.get("proofType")
    if ptype not in ("stolen", "destroyed"):
        raise https_fn.HttpsError(
            "invalid-argument", "proofType must be stolen|destroyed.")

    v = validate_ownership(uid, iid)
    is_issuer = token.get("backend") is True  # service-issued allowlist
    if not v["ok"] and not is_issuer:
        raise https_fn.HttpsError(
            "permission-denied", v.get("reason", "not-owner"))

    status = "destroyed" if ptype == "destroyed" else "stolen"
    proof_ref = db.collection("proofs").document()
    inst_ref = db.collection("cardInstances").document(iid)

    @firestore.transactional
    def _tx(t):
        snap = inst_ref.get(transaction=t)
        t.update(inst_ref, {"status": status})
        t.set(proof_ref, {
            "instanceId": iid,
            "proofType": ptype,
            "evidenceRefs": data.get("evidenceRefs", []),
            "status": "pending",  # anchor-proofs.yml picks this up
            "reporterPlayerId": uid,
            "createdAt": firestore.SERVER_TIMESTAMP,
        })
        if ptype == "destroyed":
            t.set(inst_ref.collection("ledger").document(), {
                "fromPlayerId": snap.get("currentOwnerId"),
                "toPlayerId": None,
                "transferType": "burn",
                "createdAt": firestore.SERVER_TIMESTAMP,
            })

    _tx(db.transaction())
    # on_ledger_write clears currentOwnerId from the burn row.
    return {"ok": True, "proofId": proof_ref.id, "status": status}


# ---------------------------------------------------------------------------
# 6. App identity link (decision 2026-10-12): the player enters their
#    member email in the CARDREALM app once; the app's backend calls
#    this endpoint (its own shared secret, APP_LINK_SECRET) and we
#    record players.externalIds.{system} — e.g. {base44: CR-XXXX-XXXX}.
#    Email is the join key, same as the Gumroad pipeline.
# ---------------------------------------------------------------------------

@https_fn.on_request()
def link_player_id(req: https_fn.Request) -> https_fn.Response:
    if req.method != "POST":
        return https_fn.Response("POST only", status=405)
    try:
        secret = _secret("APP_LINK_SECRET")
    except Exception:
        return https_fn.Response("server misconfigured", status=500)
    if req.headers.get("X-Link-Secret") != secret:
        return https_fn.Response("forbidden", status=403)

    body = req.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    system = body.get("system")  # e.g. "base44"
    external_id = body.get("externalId")
    if not email or not system or not external_id:
        return https_fn.Response(
            "email, system, externalId required", status=400)

    hits = list(
        db.collection("players").where("email", "==", email)
        .limit(1).stream())
    if not hits:
        return https_fn.Response("no player with that email", status=404)
    ref = hits[0].reference
    # merge=True deep-merges the map: other systems' IDs survive.
    ref.set({"externalIds": {system: str(external_id)}}, merge=True)
    return https_fn.Response(
        json.dumps({"ok": True, "uid": ref.id}),
        mimetype="application/json")
