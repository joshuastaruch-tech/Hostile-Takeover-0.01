"""Minimal Card Registry client for Arena (Python game).

Server-side only: this module uses the registry API key, so it must run on
your game server, never in a shipped client.

    from card_registry import CardRegistry

    reg = CardRegistry()  # reads CARD_REGISTRY_URL / CARD_REGISTRY_API_KEY
    profile = reg.profile("the-temp", "arena")
    if profile["is_legal"] and reg.owns(player_id, instance_id):
        ...
"""

from __future__ import annotations

import os

import requests


class CardRegistryError(RuntimeError):
    pass


class CardRegistry:
    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 timeout: int = 10):
        self.base_url = (base_url or os.environ.get("CARD_REGISTRY_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("CARD_REGISTRY_API_KEY", "")
        if not self.base_url or not self.api_key:
            raise CardRegistryError(
                "Set CARD_REGISTRY_URL and CARD_REGISTRY_API_KEY (or pass them in)."
            )
        self.timeout = timeout
        self._s = requests.Session()
        self._s.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        })
        # {(slug, game_slug): profile} — invalidate when ruleset_version changes
        self._profile_cache: dict[tuple[str, str], dict] = {}

    def _get(self, path: str, **kwargs) -> requests.Response:
        r = self._s.get(f"{self.base_url}{path}", timeout=self.timeout, **kwargs)
        if r.status_code >= 400:
            raise CardRegistryError(f"GET {path} -> {r.status_code}: {r.text[:200]}")
        return r

    # ---- definitions & per-game profiles ----

    def card(self, slug: str, version: str = "latest") -> dict:
        return self._get(f"/v1/cards/{slug}", params={"version": version}).json()

    def profile(self, slug: str, game_slug: str, use_cache: bool = True) -> dict:
        key = (slug, game_slug)
        if use_cache and key in self._profile_cache:
            return self._profile_cache[key]
        data = self._get(f"/v1/cards/{slug}/games/{game_slug}").json()
        self._profile_cache[key] = data
        return data

    def invalidate_profiles(self) -> None:
        """Call when the registry reports a new ruleset_version for your game."""
        self._profile_cache.clear()

    # ---- ownership ----

    def owns(self, player_id: str, instance_id: str) -> bool:
        """Fast 200/404 ownership check. Authoritative: call from your server."""
        r = self._s.get(
            f"{self.base_url}/v1/players/{player_id}/ownership/{instance_id}",
            timeout=self.timeout,
        )
        if r.status_code == 404:
            return False
        if r.status_code != 200:
            raise CardRegistryError(f"ownership check -> {r.status_code}: {r.text[:200]}")
        return True

    def entitlements(self, player_id: str, game_slug: str) -> list[dict]:
        return self._get(
            f"/v1/players/{player_id}/entitlements", params={"game": game_slug}
        ).json()["entitlements"]

    def instance(self, instance_id: str) -> dict:
        return self._get(f"/v1/instances/{instance_id}").json()

    # ---- writes (server-to-server, signed) ----

    def record_transfer(self, instance_id: str, to_player_id: str,
                        transfer_type: str, tx_ref: str | None = None) -> dict:
        r = self._s.post(
            f"{self.base_url}/v1/transfers",
            json={"instance_id": instance_id, "to_player_id": to_player_id,
                  "transfer_type": transfer_type, "tx_ref": tx_ref},
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise CardRegistryError(f"transfer -> {r.status_code}: {r.text[:200]}")
        return r.json()

    def report_proof(self, instance_id: str, proof_type: str,
                     evidence_refs: list[str] | None = None) -> dict:
        """Report a card stolen/destroyed. Anchors a SHA-256 proof hash
        on-chain — the system's only blockchain interaction. No wallet needed."""
        if proof_type not in ("stolen", "destroyed"):
            raise CardRegistryError("proof_type must be 'stolen' or 'destroyed'")
        r = self._s.post(
            f"{self.base_url}/v1/proofs",
            json={"instance_id": instance_id, "proof_type": proof_type,
                  "evidence_refs": evidence_refs or []},
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise CardRegistryError(f"proof -> {r.status_code}: {r.text[:200]}")
        return r.json()

    def proofs(self, instance_id: str) -> list[dict]:
        return self._get("/v1/proofs", params={"instance": instance_id}).json()["proofs"]
