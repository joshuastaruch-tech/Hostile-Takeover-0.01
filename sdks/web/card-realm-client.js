/**
 * CARDREALM browser client for MYTHOS (HTML5).
 *
 * Browser-safe: NO secrets, NO registry API key. This client talks only to
 * YOUR game server (same origin by default, session cookie auth). Your
 * server is the thing that talks to the registry — see server-proxy.example.js
 * and registry-client-node.js.
 *
 * Trust rule (from the registry README): never trust the game client on
 * ownership. Helpers here like `fieldable()` are UX-only conveniences; the
 * server re-validates everything at match start via /api/registry/decks/validate.
 *
 *   <script type="module">
 *     import { CardRealmClient } from "./card-realm-client.js";
 *     const cards = new CardRealmClient({ gameSlug: "mythos" });
 *     const profile = await cards.profile("the-temp");
 *     if (cards.fieldable(profile)) renderCard(profile);
 *     const { valid, errors, warnings } = await cards.validateDeck(deckInstanceIds);
 *   </script>
 */

export class CardRealmError extends Error {}

export class CardRealmClient {
  /**
   * @param {{ baseUrl?: string, gameSlug?: string, timeoutMs?: number }} [opts]
   *   baseUrl — your game server origin. "" = same origin (recommended).
   */
  constructor({ baseUrl = "", gameSlug = "mythos", timeoutMs = 10000 } = {}) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.gameSlug = gameSlug;
    this.timeoutMs = timeoutMs;
    // "slug" -> profile. Invalidate when your server signals a ruleset bump.
    this._profiles = new Map();
  }

  _url(path) {
    return `${this.baseUrl}${path}`;
  }

  async _json(method, path, { params, body } = {}) {
    const url = new URL(this._url(path), globalThis.location?.origin ?? "http://localhost");
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
      }
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);
    let res;
    try {
      res = await fetch(url.pathname + url.search, {
        method,
        credentials: "same-origin", // session cookie to YOUR server
        headers: {
          Accept: "application/json",
          ...(body ? { "Content-Type": "application/json" } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: ctrl.signal,
      });
    } finally {
      clearTimeout(timer);
    }
    if (res.status >= 400) {
      const text = (await res.text()).slice(0, 200);
      throw new CardRealmError(`${method} ${path} -> ${res.status}: ${text}`);
    }
    return res.status === 204 ? null : res.json();
  }

  // ---- cards & profiles (public data, proxied by your server) ----

  /** @returns {Promise<object>} definition + media slots for a card slug */
  card(slug, version = "latest") {
    return this._json("GET", `/api/registry/cards/${encodeURIComponent(slug)}`, {
      params: { version },
    });
  }

  /**
   * Per-game profile for MYTHOS (cached). Cost/power/legality.
   * @returns {Promise<object>}
   */
  async profile(slug, { useCache = true } = {}) {
    if (useCache && this._profiles.has(slug)) return this._profiles.get(slug);
    const data = await this._json(
      "GET",
      `/api/registry/cards/${encodeURIComponent(slug)}/profile`,
      { params: { game: this.gameSlug } }
    );
    this._profiles.set(slug, data);
    return data;
  }

  /** Call when your server pushes a rulesetVersion bump for MYTHOS. */
  invalidateProfiles() {
    this._profiles.clear();
  }

  /**
   * UX-only legality hint. NOT authoritative — the server re-validates
   * every deck at match start (see validateDeck).
   */
  fieldable(profile) {
    return profile?.is_legal === true;
  }

  // ---- player-scoped reads (server derives the player from the session) ----

  /** @returns {Promise<object[]>} cards this player can field in MYTHOS */
  async entitlements() {
    const data = await this._json("GET", "/api/registry/entitlements", {
      params: { game: this.gameSlug },
    });
    return data.entitlements ?? data;
  }

  /**
   * Do I own this instance? Server-side answer, no secrets in the browser.
   * @returns {Promise<{ owns: boolean }>}
   */
  async owns(instanceId) {
    const data = await this._json(
      "GET",
      `/api/registry/ownership/${encodeURIComponent(instanceId)}`
    );
    return { owns: data?.owns === true };
  }

  /**
   * Ask YOUR server to validate a deck authoritatively (ownership +
   * legality, from the registry). Call at deck save AND match start.
   * @param {string[]} instanceIds
   * @returns {Promise<{ valid: boolean, fielded: object[], errors: object[], warnings: object[] }>}
   */
  validateDeck(instanceIds) {
    return this._json("POST", "/api/registry/decks/validate", {
      body: { instance_ids: instanceIds, game: this.gameSlug },
    });
  }

  // ---- reports (server must gate these to moderators/owners) ----

  /**
   * Report a card stolen/destroyed. Your server MUST restrict this endpoint
   * (e.g. moderator role or verified owner) — the browser just forwards.
   */
  reportProof(instanceId, proofType, evidenceRefs = []) {
    if (!["stolen", "destroyed"].includes(proofType)) {
      throw new CardRealmError("proofType must be 'stolen' or 'destroyed'");
    }
    return this._json("POST", "/api/registry/proofs", {
      body: {
        instance_id: instanceId,
        proof_type: proofType,
        evidence_refs: evidenceRefs,
      },
    });
  }
}
