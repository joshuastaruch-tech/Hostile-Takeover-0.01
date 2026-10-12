#!/usr/bin/env python3
"""Batch-anchor pending stolen/destroyed proof hashes on-chain.

Runs from .github/workflows/anchor-proofs.yml (twice daily). The Spark
plan blocks outbound non-Google calls from Cloud Functions, so the one
blockchain interaction in the system lives here instead of in a function.

Env vars:
  FIREBASE_SERVICE_ACCOUNT  JSON of a Firebase service-account key
  CHAIN_RPC_URL             e.g. a free Alchemy/Infura HTTPS endpoint
  ANCHOR_PRIVATE_KEY        funded keypair holding a few cents of gas
  PROOF_CHAIN               label stored on the proof row (default: "evm")

Each run: for every `proofs` doc with status == 'pending', build the
canonical proof JSON (same definition as firestore/data-model.md),
SHA-256 it, submit one EVM transaction carrying the hash in its data
field, and mark the proof `anchored` (or `failed` with an error).
"""
import hashlib
import json
import os
import sys

import firebase_admin
from firebase_admin import credentials, firestore
from web3 import Web3


def canonical_proof_json(proof: dict, instance: dict) -> str:
    """Canonical form hashed into evidenceHash. Field order is fixed
    (sort_keys) so anyone can recompute and verify the anchored hash."""
    def_ref = instance.get("definitionRef", "") or ""
    slug = def_ref.split("/")[-1].rsplit("__v", 1)[0] if def_ref else ""
    payload = {
        "proofId": proof["id"],
        "instanceId": proof["instanceId"],
        "definitionSlug": slug,
        "serial": instance.get("serial"),
        "proofType": proof["proofType"],
        "reporterPlayerId": proof["reporterPlayerId"],
        "createdAt": proof["createdAt"].isoformat(),
        "evidenceRefs": sorted(proof.get("evidenceRefs", [])),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def submit_anchor_tx(w3: Web3, key: str, evidence_hash: str) -> str:
    """One memo transaction to self; the hash rides in the data field."""
    acct = w3.eth.account.from_key(key)
    tx = {
        "from": acct.address,
        "to": acct.address,
        "value": 0,
        "data": w3.to_hex(text=f"cardrealm-proof:{evidence_hash}"),
        "chainId": w3.eth.chain_id,
        "gasPrice": w3.eth.gas_price,
        "nonce": w3.eth.get_transaction_count(acct.address),
    }
    tx["gas"] = w3.eth.estimate_gas(tx)
    signed = acct.sign_transaction(tx)
    return w3.eth.send_raw_transaction(signed.raw_transaction).hex()


def main() -> int:
    firebase_admin.initialize_app(
        credentials.Certificate(json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT"]))
    )
    db = firestore.client()

    w3 = Web3(Web3.HTTPProvider(os.environ["CHAIN_RPC_URL"]))
    if not w3.is_connected():
        print("ERROR: cannot reach CHAIN_RPC_URL", file=sys.stderr)
        return 1
    key = os.environ["ANCHOR_PRIVATE_KEY"]
    chain_label = os.environ.get("PROOF_CHAIN", "evm")

    pending = db.collection("proofs").where("status", "==", "pending").stream()
    count = 0
    for snap in pending:
        proof = snap.to_dict() or {}
        proof["id"] = snap.id
        inst_snap = db.collection("cardInstances").document(
            proof["instanceId"]
        ).get()
        instance = inst_snap.to_dict() or {}
        canonical = canonical_proof_json(proof, instance)
        evidence_hash = hashlib.sha256(canonical.encode()).hexdigest()
        try:
            tx_hash = submit_anchor_tx(w3, key, evidence_hash)
            snap.reference.update(
                {
                    "evidenceHash": evidence_hash,
                    "chain": chain_label,
                    "txHash": tx_hash,
                    "status": "anchored",
                    "anchoredAt": firestore.SERVER_TIMESTAMP,
                }
            )
            print(f"anchored {snap.id} -> {tx_hash}")
        except Exception as exc:  # noqa: BLE001 — record and keep going
            snap.reference.update({"status": "failed", "error": str(exc)[:500]})
            print(f"FAILED {snap.id}: {exc}", file=sys.stderr)
        count += 1
    print(f"done: {count} proof(s) processed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
