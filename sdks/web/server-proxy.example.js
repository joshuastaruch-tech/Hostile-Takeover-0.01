/**
 * Example: MYTHOS game-server proxy between the browser client
 * (card-realm-client.js) and the registry.
 *
 * Copy the handlers you need into your MYTHOS server (Express 4/5 shown).
 * The browser client expects exactly these routes — see README.md.
 *
 * Security model:
 *  - The registry API key lives ONLY here (process env), never in the browser.
 *  - The player id comes from YOUR session (cookie/JWT), never from the client.
 *  - reportProof is gated: wire `requireModerator` to your real role check.
 *
 * Requires: npm i express
 * Env: CARD_REGISTRY_URL, CARD_REGISTRY_API_KEY
 */

import express from "express";
import { CardRegistry, CardRegistryError } from "./registry-client-node.js";

const GAME_SLUG = "mythos";

const reg = new CardRegistry();

// Replace with your real session lookup. Must return the player's registry
// player id (or null when signed out).
function getPlayerId(req) {
  return req.session?.playerId ?? req.user?.playerId ?? null;
}

// Replace with your real moderator/owner check for reportProof.
function requireModerator(req, res, next) {
  // e.g. if (!req.user?.roles?.includes("moderator")) return res.status(403).json({ error: "forbidden" });
  next();
}

function registryError(res, err) {
  const status = err instanceof CardRegistryError ? 502 : 500;
  res.status(status).json({ error: err.message });
}

export function registryRouter() {
  const r = express.Router();
  r.use(express.json());

  // GET /api/registry/cards/:slug?version=latest — public definition info
  r.get("/api/registry/cards/:slug", async (req, res) => {
    try {
      res.json(await reg.card(req.params.slug, req.query.version ?? "latest"));
    } catch (err) {
      registryError(res, err);
    }
  });

  // GET /api/registry/cards/:slug/profile?game=mythos — per-game profile
  r.get("/api/registry/cards/:slug/profile", async (req, res) => {
    try {
      res.json(await reg.profile(req.params.slug, req.query.game ?? GAME_SLUG));
    } catch (err) {
      registryError(res, err);
    }
  });

  // GET /api/registry/entitlements?game=mythos — what this player can field
  r.get("/api/registry/entitlements", async (req, res) => {
    const playerId = getPlayerId(req);
    if (!playerId) return res.status(401).json({ error: "not signed in" });
    try {
      res.json({ entitlements: await reg.entitlements(playerId, req.query.game ?? GAME_SLUG) });
    } catch (err) {
      registryError(res, err);
    }
  });

  // GET /api/registry/ownership/:instanceId — { owns: true|false }
  r.get("/api/registry/ownership/:instanceId", async (req, res) => {
    const playerId = getPlayerId(req);
    if (!playerId) return res.status(401).json({ error: "not signed in" });
    try {
      res.json({ owns: await reg.owns(playerId, req.params.instanceId) });
    } catch (err) {
      registryError(res, err);
    }
  });

  // POST /api/registry/decks/validate { instance_ids[], game? }
  // Authoritative deck check: ownership + legality from the registry.
  // Call at deck save AND at match start — never trust the client.
  r.post("/api/registry/decks/validate", async (req, res) => {
    const playerId = getPlayerId(req);
    if (!playerId) return res.status(401).json({ error: "not signed in" });
    const ids = req.body?.instance_ids;
    if (!Array.isArray(ids) || ids.length === 0) {
      return res.status(400).json({ error: "instance_ids must be a non-empty array" });
    }
    const game = req.body?.game ?? GAME_SLUG;
    try {
      const fielded = [];
      const errors = [];
      const warnings = [];
      for (const iid of ids) {
        const owned = await reg.owns(playerId, iid);
        if (!owned) {
          // Distinguish "card was destroyed" from "never yours / not found".
          let status = null;
          try {
            status = (await reg.instance(iid)).status;
          } catch {
            /* instance unreadable — keep generic error */
          }
          errors.push({
            instance_id: iid,
            code: status === "destroyed" ? "destroyed" : "not_owned",
          });
          continue;
        }
        const inst = await reg.instance(iid);
        // Registry API field for the card slug; adjust the accessors if your
        // API names it differently (definitionSlug / slug).
        const slug = inst.definition_slug ?? inst.definitionSlug ?? inst.slug;
        if (!slug) {
          errors.push({ instance_id: iid, code: "unknown_definition" });
          continue;
        }
        const prof = await reg.profile(slug, game);
        if (prof.is_legal !== true) {
          errors.push({
            instance_id: iid,
            card_slug: slug,
            code: "not_legal",
            detail: prof.banned_reason ?? prof.bannedReason ?? null,
          });
          continue;
        }
        if (inst.status === "stolen") {
          // Still yours per the ledger — but flag it for the UI.
          warnings.push({ instance_id: iid, card_slug: slug, code: "stolen_warning" });
        }
        fielded.push({ instance_id: iid, card_slug: slug });
      }
      res.json({ valid: errors.length === 0, fielded, errors, warnings });
    } catch (err) {
      registryError(res, err);
    }
  });

  // POST /api/registry/proofs — report stolen/destroyed (gated!)
  r.post("/api/registry/proofs", requireModerator, async (req, res) => {
    const { instance_id, proof_type, evidence_refs } = req.body ?? {};
    if (!instance_id || !proof_type) {
      return res.status(400).json({ error: "instance_id and proof_type are required" });
    }
    try {
      res.status(201).json(await reg.reportProof(instance_id, proof_type, evidence_refs ?? []));
    } catch (err) {
      registryError(res, err);
    }
  });

  return r;
}

// ---- standalone usage ----------------------------------------------------
// app.use(registryRouter());
//
// For a quick smoke test (needs CARD_REGISTRY_URL / CARD_REGISTRY_API_KEY):
//   node server-proxy.example.js
// listens on :8787 with the router mounted.
if (process.argv[1] === new URL(import.meta.url).pathname) {
  const app = express();
  app.use(registryRouter());
  app.listen(8787, () => console.log("mythos registry proxy on :8787"));
}
