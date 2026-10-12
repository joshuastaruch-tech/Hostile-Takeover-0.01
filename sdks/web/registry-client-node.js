/**
 * Card Registry client for game servers (Node 18+).
 *
 * Server-side ONLY: this module uses CARD_REGISTRY_API_KEY, so it must run
 * on your game server. Never bundle it into a shipped client (especially
 * the MYTHOS HTML5 build).
 *
 * Mirrors sdks/python/card_registry.py method-for-method, so Arena and MYTHOS
 * share the same registry semantics.
 *
 *   import { CardRegistry } from "./registry-client-node.js";
 *   const reg = new CardRegistry(); // reads CARD_REGISTRY_URL / CARD_REGISTRY_API_KEY
 *   const profile = await reg.profile("the-temp", "mythos");
 *   if (profile.is_legal && await reg.owns(playerId, instanceId)) { ... }
 */

export class CardRegistryError extends Error {}

export class CardRegistry {
  /**
   * @param {{ baseUrl?: string, apiKey?: string, timeoutMs?: number }} [opts]
   */
  constructor({ baseUrl, apiKey, timeoutMs = 10000 } = {}) {
    this.baseUrl = (baseUrl ?? process.env.CARD_REGISTRY_URL ?? "").replace(/\/+$/, "");
    this.apiKey = apiKey ?? process.env.CARD_REGISTRY_API_KEY ?? "";
    if (!this.baseUrl || !this.apiKey) {
      throw new CardRegistryError(
        "Set CARD_REGISTRY_URL and CARD_REGISTRY_API_KEY (or pass them in)."
      );
    }
    this.timeoutMs = timeoutMs;
    // "slug|gameSlug" -> profile. Drop it when the registry bumps
    // games/{gameSlug}.rulesetVersion for your game.
    this._profiles = new Map();
  }

  async _request(method, path, { params, body } = {}) {
    const url = new URL(`${this.baseUrl}${path}`);
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
      }
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      return await fetch(url, {
        method,
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          Accept: "application/json",
          ...(body ? { "Content-Type": "application/json" } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: ctrl.signal,
      });
    } finally {
      clearTimeout(timer);
    }
  }

  async _json(method, path, opts = {}) {
    const res = await this._request(method, path, opts);
    if (res.status >= 400) {
      const text = (await res.text()).slice(0, 200);
      throw new CardRegistryError(`${method} ${path} -> ${res.status}: ${text}`);
    }
    return res.json();
  }

  // ---- definitions & per-game profiles ----

  /** @returns {Promise<object>} definition + media slots */
  card(slug, version = "latest") {
    return this._json("GET", `/v1/cards/${encodeURIComponent(slug)}`, {
      params: { version },
    });
  }

  /** @returns {Promise<object>} per-game profile: cost/power/legality (cached) */
  async profile(slug, gameSlug, { useCache = true } = {}) {
    const key = `${slug}|${gameSlug}`;
    if (useCache && this._profiles.has(key)) return this._profiles.get(key);
    const data = await this._json(
      "GET",
      `/v1/cards/${encodeURIComponent(slug)}/games/${encodeURIComponent(gameSlug)}`
    );
    this._profiles.set(key, data);
    return data;
  }

  /** Call when the registry reports a new rulesetVersion for your game. */
  invalidateProfiles() {
    this._profiles.clear();
  }

  // ---- ownership ----

  /**
   * Fast 200/404 ownership check. Authoritative: call from your server.
   * @returns {Promise<boolean>}
   */
  async owns(playerId, instanceId) {
    const res = await this._request(
      "GET",
      `/v1/players/${encodeURIComponent(playerId)}/ownership/${encodeURIComponent(instanceId)}`
    );
    if (res.status === 404) return false;
    if (res.status !== 200) {
      const text = (await res.text()).slice(0, 200);
      throw new CardRegistryError(`ownership check -> ${res.status}: ${text}`);
    }
    return true;
  }

  /** @returns {Promise<object[]>} what a player can field in a game */
  async entitlements(playerId, gameSlug) {
    const data = await this._json(
      "GET",
      `/v1/players/${encodeURIComponent(playerId)}/entitlements`,
      { params: { game: gameSlug } }
    );
    return data.entitlements;
  }

  /** @returns {Promise<object>} instance + current owner + NFT/physical links */
  instance(instanceId) {
    return this._json("GET", `/v1/instances/${encodeURIComponent(instanceId)}`);
  }

  // ---- writes (server-to-server, signed) ----

  /**
   * Record sale/trade/mint/burn. Appends to the ownership ledger.
   * @param {{ instanceId: string, toPlayerId: string, transferType: string, txRef?: string|null }} args
   */
  recordTransfer({ instanceId, toPlayerId, transferType, txRef = null }) {
    return this._json("POST", "/v1/transfers", {
      body: {
        instance_id: instanceId,
        to_player_id: toPlayerId,
        transfer_type: transferType,
        tx_ref: txRef,
      },
    });
  }

  /**
   * Report a card stolen/destroyed. Anchors a SHA-256 proof hash on-chain —
   * the system's only blockchain interaction. No wallet needed.
   */
  reportProof(instanceId, proofType, evidenceRefs = []) {
    if (!["stolen", "destroyed"].includes(proofType)) {
      throw new CardRegistryError("proofType must be 'stolen' or 'destroyed'");
    }
    return this._json("POST", "/v1/proofs", {
      body: {
        instance_id: instanceId,
        proof_type: proofType,
        evidence_refs: evidenceRefs,
      },
    });
  }

  /** @returns {Promise<object[]>} anchoring proofs for an instance */
  async proofs(instanceId) {
    const data = await this._json("GET", "/v1/proofs", {
      params: { instance: instanceId },
    });
    return data.proofs;
  }
}
