#!/usr/bin/env python3
"""Reconcile registry membership entitlements against Gumroad.

Runs from .github/workflows/gumroad-reconcile.yml (twice daily). The
real-time path (Gumroad ping -> Wix endpoint -> mint_auth_token sync)
grants entitlements; this sweep is the safety net: any membership
entitlement Gumroad no longer confirms as active gets revoked here,
and confirmed memberships with no registry player are reported.
Grants stay on the real-time path — this script only revokes/reports.

Env vars:
  FIREBASE_SERVICE_ACCOUNT  JSON of a Firebase service-account key
  GUMROAD_ACCESS_TOKEN      Gumroad API access token (read scope is fine)

Usage: python scripts/reconcile_gumroad.py [--dry-run]
"""
import argparse
import json
import os
import sys
import urllib.request

import firebase_admin
from firebase_admin import credentials, firestore

GUMROAD_API = "https://api.gumroad.com/v2"

# TODO(Joshua): real Gumroad product IDs. Mirrored in
# wix/backend/gumroad-http-functions.js and firestore/data-model.md.
PRODUCT_TIER_MAP = {
    # "PRODUCT_ID": {"tier": "cultist", "gameSlugs": ["mythos"]},
}

ACTIVE_STATUSES = {"alive", "pending_cancellation", "pending_failure"}


def gumroad_get(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{GUMROAD_API}{path}",
        headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read())


def confirmed_memberships(token: str) -> dict:
    """email -> set of (tier, gameSlug) Gumroad currently confirms."""
    confirmed: dict[str, set] = {}
    for product_id, mapped in PRODUCT_TIER_MAP.items():
        url = f"/products/{product_id}/subscribers"
        while url:
            data = gumroad_get(url, token)
            for sub in data.get("subscribers", []):
                if sub.get("status") in ACTIVE_STATUSES:
                    email = (sub.get("email") or "").strip().lower()
                    if email:
                        for game in mapped["gameSlugs"]:
                            confirmed.setdefault(email, set()).add(
                                (mapped["tier"], game))
            nxt = data.get("next_page_url")
            url = nxt.removeprefix(GUMROAD_API) if nxt else None
    return confirmed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="report only, change nothing")
    args = parser.parse_args()

    firebase_admin.initialize_app(
        credentials.Certificate(
            json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT"])))
    db = firestore.client()
    token = os.environ["GUMROAD_ACCESS_TOKEN"]

    if not PRODUCT_TIER_MAP:
        print("PRODUCT_TIER_MAP is empty — nothing to reconcile yet.")
        return 0

    confirmed = confirmed_memberships(token)

    # Resolve confirmed emails to registry player UIDs (email is the
    # join key across Gumroad, Wix, and the registry).
    expected = set()  # (uid, gameSlug) that should hold an entitlement
    for email, grants in confirmed.items():
        hits = list(db.collection("players")
                    .where("email", "==", email).limit(1).stream())
        if not hits:
            print(f"WARN confirmed member has no registry player: {email}")
            continue
        uid = hits[0].id
        for _tier, game in grants:
            expected.add((uid, game))

    revoked = 0
    ents = (db.collection("entitlements")
            .where("source", "==", "membership").stream())
    for doc in ents:
        d = doc.to_dict()
        if d.get("revokedAt") is not None:
            continue
        if (d.get("playerId"), d.get("gameSlug")) not in expected:
            print(f"REVOKE {doc.id} player={d.get('playerId')} "
                  f"game={d.get('gameSlug')}")
            if not args.dry_run:
                doc.reference.set(
                    {"revokedAt": firestore.SERVER_TIMESTAMP}, merge=True)
            revoked += 1
    print(f"Done. confirmed={len(expected)} revoked={revoked} "
          f"dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
