#!/usr/bin/env python3
"""Behavioral tests for functions/main.py — no Firebase account needed.

The Firebase boundary (firebase_functions, firebase_admin, google.cloud)
is stubbed with in-memory fakes, then the REAL functions/main.py is
imported and exercised: auth bridge login/sync branches, tier grants
(idempotency + revoke), claim flow, ledger mirror, proof reports.

Run:  python3 tests/test_registry_functions.py
Exit code 0 = all checks passed.
"""
import hashlib
import importlib.util
import json
import os
import sys
import types

os.environ["GCLOUD_PROJECT"] = "test-project"
SECRET = "test-secret"

# ---------------------------------------------------------------------------
# In-memory Firestore fake
# ---------------------------------------------------------------------------

STORE: dict[tuple, dict] = {}
_auto = [0]


def _deep_merge(dst, src):
    """Firestore merge=True semantics: nested maps merge recursively."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v


class Snapshot:
    def __init__(self, ref, data):
        self._ref = ref
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    @property
    def id(self):
        return self._ref.id

    @property
    def reference(self):
        return self._ref

    def to_dict(self):
        return dict(self._data) if self._data else None

    def get(self, field):
        return (self._data or {}).get(field)


class DocumentRef:
    def __init__(self, path):
        self._path = path  # tuple: (coll, id, coll, id, ...)

    @property
    def id(self):
        return self._path[-1]

    def get(self, transaction=None):
        return Snapshot(self, STORE.get(self._path))

    def set(self, data, merge=False):
        if merge and self._path in STORE:
            _deep_merge(STORE[self._path], data)
        else:
            STORE[self._path] = dict(data)

    def update(self, data):
        STORE.setdefault(self._path, {}).update(data)

    def collection(self, name):
        return CollectionRef(self._path + (name,))


class Query:
    def __init__(self, path, filters=(), limit_n=None):
        self._path, self._filters, self._limit = path, filters, limit_n

    def where(self, field, op, value):
        assert op == "=="
        return Query(self._path, self._filters + ((field, value),),
                     self._limit)

    def limit(self, n):
        return Query(self._path, self._filters, n)

    def stream(self):
        out = []
        for path, data in STORE.items():
            if path[:-1] == self._path and len(path) == len(self._path) + 1:
                if all(data.get(f) == v for f, v in self._filters):
                    out.append(Snapshot(DocumentRef(path), data))
        return iter(out[: self._limit] if self._limit else out)


class CollectionRef:
    def __init__(self, path):
        self._path = path

    def document(self, doc_id=None):
        if doc_id is None:
            _auto[0] += 1
            doc_id = f"auto{_auto[0]}"
        return DocumentRef(self._path + (doc_id,))

    def where(self, field, op, value):
        return Query(self._path).where(field, op, value)

    def stream(self):
        return Query(self._path).stream()


class FakeTransaction:
    def set(self, ref, data):
        ref.set(data)

    def update(self, ref, data):
        ref.update(data)


class FakeFirestore:
    def collection(self, name):
        return CollectionRef((name,))

    def transaction(self):
        return FakeTransaction()


FAKE_DB = FakeFirestore()
SERVER_TIMESTAMP = object()  # sentinel; identity-checked in tests

# ---------------------------------------------------------------------------
# Stub modules (installed before importing functions/main.py)
# ---------------------------------------------------------------------------

def _identity_decorator_factory(*a, **k):
    return lambda fn: fn


ff = types.ModuleType("firebase_functions")
ff.options = types.SimpleNamespace(set_global_options=lambda **k: None)
ff.firestore_fn = types.SimpleNamespace(
    on_document_created=_identity_decorator_factory,
    on_document_written=_identity_decorator_factory,
    Event=object, DocumentSnapshot=object, Change=object)
ff.https_fn = types.SimpleNamespace(
    on_call=_identity_decorator_factory,
    on_request=_identity_decorator_factory,
    CallableRequest=object, Request=object)


class HttpsError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


class FakeResponse:
    def __init__(self, body="", status=200, mimetype=None):
        self.body, self.status = body, status


ff.https_fn.HttpsError = HttpsError
ff.https_fn.Response = FakeResponse
sys.modules["firebase_functions"] = ff

fa = types.ModuleType("firebase_admin")
fa.initialize_app = lambda *a, **k: None
_auth_users: dict[str, dict] = {}


class UserNotFoundError(Exception):
    pass


fa_auth = types.SimpleNamespace(
    UserNotFoundError=UserNotFoundError,
    get_user=lambda uid: _auth_users[uid] if uid in _auth_users
    else (_ for _ in ()).throw(UserNotFoundError(uid)),
    create_user=lambda uid, email=None, display_name=None:
    _auth_users.__setitem__(uid, {"email": email}) or
    types.SimpleNamespace(uid=uid),
    create_custom_token=lambda uid: f"token-for-{uid}".encode(),
)
fa.auth = fa_auth
fa.firestore = types.SimpleNamespace(
    client=lambda: FAKE_DB,
    SERVER_TIMESTAMP=SERVER_TIMESTAMP,
    transactional=lambda fn: fn,
)
sys.modules["firebase_admin"] = fa

google = types.ModuleType("google")
gcloud = types.ModuleType("google.cloud")
published: list[bytes] = []


class _PubFuture:
    def result(self):
        return None


class _Publisher:
    def topic_path(self, project, topic):
        return f"projects/{project}/topics/{topic}"

    def publish(self, topic, data):
        published.append(data)
        return _PubFuture()


class _SecretResp:
    payload = types.SimpleNamespace(data=SECRET.encode())


class _Secrets:
    def access_secret_version(self, request=None):
        return _SecretResp()


gcloud.pubsub_v1 = types.SimpleNamespace(PublisherClient=_Publisher)
gcloud.secretmanager = types.SimpleNamespace(
    SecretManagerServiceClient=_Secrets)
google.cloud = gcloud
sys.modules["google"] = google
sys.modules["google.cloud"] = gcloud
sys.modules["google.cloud.pubsub_v1"] = gcloud.pubsub_v1
sys.modules["google.cloud.secretmanager"] = gcloud.secretmanager

# ---------------------------------------------------------------------------
# Import the real functions module
# ---------------------------------------------------------------------------

spec = importlib.util.spec_from_file_location(
    "registry_main",
    os.path.join(os.path.dirname(__file__), "..", "functions", "main.py"))
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)

# ---------------------------------------------------------------------------
# Tiny test framework
# ---------------------------------------------------------------------------

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok  {name}")
    else:
        failed += 1
        print(f"FAIL  {name}")


class HttpReq:
    def __init__(self, body, secret=SECRET, method="POST"):
        self.method = method
        self.headers = {"X-Webhook-Secret": secret}
        self._body = body

    def get_json(self, silent=True):
        return self._body


def callable_req(data, uid="player1", token=None):
    auth = None if uid is None else {"uid": uid, "token": token or {}}
    return types.SimpleNamespace(data=data, auth=auth)


def expect_https_error(name, code, fn):
    try:
        fn()
    except HttpsError as e:
        check(name, e.code == code)
    else:
        check(name + " (no error raised)", False)


# ---------------------------------------------------------------------------
# mint_auth_token — login branch
# ---------------------------------------------------------------------------

print("mint_auth_token")
r = main.mint_auth_token(HttpReq(
    {"wixMemberId": "42", "email": "a@x.io", "displayName": "Ana"}))
body = json.loads(r.body)
check("login returns 200 + token", r.status == 200 and
      body.get("token") == "token-for-wix_42")
p = STORE.get(("players", "wix_42"))
check("login upserts players/wix_42", p and p["wixMemberId"] == "42")

# sync branch — no token, no tier
r = main.mint_auth_token(HttpReq(
    {"wixMemberId": "42", "purpose": "sync", "email": "a@x.io"}))
body = json.loads(r.body)
check("sync returns ok, no token", body.get("ok") is True and
      "token" not in body and body.get("granted") == [])

# sync with tier grant
r = main.mint_auth_token(HttpReq({
    "wixMemberId": "42", "purpose": "sync", "tier": "operative",
    "gameSlugs": ["mythos"], "sourceEventId": "sale_1"}))
body = json.loads(r.body)
ent = STORE.get(("entitlements", "membership_wix_42_mythos"))
check("tier grant returns granted games", body.get("granted") == ["mythos"])
check("membership entitlement written", ent and ent["tier"] == "operative"
      and ent["source"] == "membership" and ent["instanceId"] is None
      and ent["revokedAt"] is None
      and ent["grantedAt"] is SERVER_TIMESTAMP)
check("gumroad event logged", ("gumroadEvents", "sale_1") in STORE)
granted_at = ent["grantedAt"]

# idempotency — same event again, grantedAt must not move
main.mint_auth_token(HttpReq({
    "wixMemberId": "42", "purpose": "sync", "tier": "operative",
    "gameSlugs": ["mythos"], "sourceEventId": "sale_1"}))
ent2 = STORE.get(("entitlements", "membership_wix_42_mythos"))
check("re-processing is idempotent", ent2["grantedAt"] is granted_at)

# on_entitlement_write fans out to Pub/Sub with the tier
ev = types.SimpleNamespace(
    params={"entitlementId": "membership_wix_42_mythos"},
    data=types.SimpleNamespace(
        after=Snapshot(DocumentRef(("entitlements", "x")), ent2),
        before=None))
main.on_entitlement_write(ev)
payload = json.loads(published[-1])
check("entitlement fan-out carries tier", payload["tier"] == "operative"
      and payload["revoked"] is False)

# sync revoke
r = main.mint_auth_token(HttpReq({
    "wixMemberId": "42", "purpose": "sync", "tier": "operative",
    "gameSlugs": ["mythos"], "revoke": True, "sourceEventId": "sale_1"}))
ent3 = STORE.get(("entitlements", "membership_wix_42_mythos"))
check("revoke sets revokedAt", ent3["revokedAt"] is SERVER_TIMESTAMP)
check("partial syncs never clobber stored email",
      STORE[("players", "wix_42")].get("email") == "a@x.io")

# auth failures
r = main.mint_auth_token(HttpReq({"wixMemberId": "42"}, secret="wrong"))
check("wrong secret -> 403", r.status == 403)
r = main.mint_auth_token(HttpReq({"email": "a@x.io"}))
check("missing wixMemberId -> 400", r.status == 400)
r = main.mint_auth_token(HttpReq({"wixMemberId": "42"}, method="GET"))
check("GET -> 405", r.status == 405)

# ---------------------------------------------------------------------------
# claim_card + on_ledger_write
# ---------------------------------------------------------------------------

print("claim_card")
digest = hashlib.sha256(b"CODE-123").hexdigest()
STORE[("cardInstances", "inst1")] = {
    "claimCodeHash": digest, "status": "active", "currentOwnerId": None}

out = main.claim_card(callable_req(
    {"claimCode": "CODE-123", "gameSlug": "mythos"}))
check("claim succeeds", out == {"ok": True, "instanceId": "inst1"})
ledger = list(FAKE_DB.collection("cardInstances").document("inst1")
              .collection("ledger").stream())
check("claim writes ledger row", len(ledger) == 1 and
      ledger[0].to_dict()["toPlayerId"] == "player1" and
      ledger[0].to_dict()["transferType"] == "claim")
ents = [d.to_dict() for d in FAKE_DB.collection("entitlements").stream()
        if d.to_dict().get("instanceId") == "inst1"]
check("claim writes entitlement", len(ents) == 1 and
      ents[0]["playerId"] == "player1")

ev = types.SimpleNamespace(params={"instanceId": "inst1"}, data=ledger[0])
main.on_ledger_write(ev)
check("ledger mirror sets currentOwnerId",
      STORE[("cardInstances", "inst1")]["currentOwnerId"] == "player1")

expect_https_error("second claim -> already-exists", "already-exists",
                   lambda: main.claim_card(callable_req(
                       {"claimCode": "CODE-123", "gameSlug": "mythos"},
                       uid="player2")))
expect_https_error("unknown code -> not-found", "not-found",
                   lambda: main.claim_card(callable_req(
                       {"claimCode": "NOPE", "gameSlug": "mythos"})))
expect_https_error("no auth -> unauthenticated", "unauthenticated",
                   lambda: main.claim_card(callable_req(
                       {"claimCode": "CODE-123", "gameSlug": "mythos"},
                       uid=None)))

# ---------------------------------------------------------------------------
# validate_ownership + report_proof
# ---------------------------------------------------------------------------

print("report_proof / validate_ownership")
check("owner validates", main.validate_ownership("player1", "inst1")
      == {"ok": True})
check("stranger does not", main.validate_ownership("player2", "inst1")
      == {"ok": False, "reason": "not-owner"})

out = main.report_proof(callable_req(
    {"instanceId": "inst1", "proofType": "destroyed"}))
check("destroy report ok", out["ok"] is True and out["status"] == "destroyed")
check("instance marked destroyed",
      STORE[("cardInstances", "inst1")]["status"] == "destroyed")
proofs = [d.to_dict() for d in FAKE_DB.collection("proofs").stream()]
check("proof pending for anchoring", len(proofs) == 1 and
      proofs[0]["status"] == "pending")
ledger = list(FAKE_DB.collection("cardInstances").document("inst1")
              .collection("ledger").stream())
burns = [d.to_dict() for d in ledger
         if d.to_dict()["transferType"] == "burn"]
check("burn ledger row written", len(burns) == 1 and
      burns[0]["toPlayerId"] is None)
check("destroyed no longer validates",
      main.validate_ownership("player1", "inst1")
      == {"ok": False, "reason": "destroyed"})
expect_https_error("non-owner report -> permission-denied",
                   "permission-denied",
                   lambda: main.report_proof(callable_req(
                       {"instanceId": "inst1", "proofType": "stolen"},
                       uid="player2")))

# ---------------------------------------------------------------------------
# link_player_id — Base44 identity link (email join key)
# ---------------------------------------------------------------------------

print("link_player_id")


class LinkReq:
    def __init__(self, body, secret=SECRET, method="POST"):
        self.method = method
        self.headers = {"X-Link-Secret": secret}
        self._body = body

    def get_json(self, silent=True):
        return self._body


# players/wix_42 has email a@x.io (created by the login test above);
# give it a pre-existing mythos ID to prove deep-merge preserves it.
STORE[("players", "wix_42")]["externalIds"] = {"mythos": "game-uid-1"}
r = main.link_player_id(LinkReq({
    "email": "  A@x.io", "system": "base44",
    "externalId": "CR-1234-5678"}))
body = json.loads(r.body)
ext = STORE[("players", "wix_42")].get("externalIds", {})
check("link returns ok + uid", r.status == 200 and body.get("uid")
      == "wix_42")
check("base44 ID recorded", ext.get("base44") == "CR-1234-5678")
check("other systems' IDs preserved", ext.get("mythos") == "game-uid-1")
r = main.link_player_id(LinkReq({
    "email": "a@x.io", "system": "base44", "externalId": "CR-1234-5678"}))
check("re-link is idempotent", r.status == 200)
r = main.link_player_id(LinkReq({
    "email": "ghost@x.io", "system": "base44", "externalId": "CR-1"}))
check("unknown email -> 404", r.status == 404)
r = main.link_player_id(LinkReq({
    "email": "a@x.io", "system": "base44", "externalId": "CR-1"},
    secret="wrong"))
check("wrong secret -> 403", r.status == 403)
r = main.link_player_id(LinkReq({"email": "a@x.io"}))
check("missing fields -> 400", r.status == 400)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
