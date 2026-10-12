-- ============================================================
-- Card Registry — initial schema (Postgres 14+)
--
-- Three-layer model:
--   1. card_definitions  = what a card IS (canonical, versioned)
--   2. card_instances    = which COPY (physical print, digital copy, NFT token)
--   3. ownership_ledger  = who held it WHEN (append-only provenance)
--
-- game_card_profiles is the multi-game hinge: one canonical card maps
-- into each game's own stats/legality without forking its identity.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------- identity ----------------

CREATE TABLE issuers (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name       TEXT NOT NULL,
  slug       TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE players (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  display_name TEXT,
  email        TEXT UNIQUE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Phase 2 (deferred): on-chain wallets. Kept in the model for later;
-- Phase 1 validates NFT ownership internally from the ledger.
CREATE TABLE wallets (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id   UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  chain       TEXT NOT NULL,              -- 'ethereum', 'solana', ...
  address     TEXT NOT NULL,
  verified_at TIMESTAMPTZ,                -- set after signature challenge
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (chain, address)
);

-- ---------------- cards ----------------

CREATE TABLE card_definitions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  issuer_id     UUID NOT NULL REFERENCES issuers(id),
  slug          TEXT NOT NULL,            -- 'the-temp'
  name          TEXT NOT NULL,            -- 'The Temp'
  type_line     TEXT NOT NULL,            -- 'Creature · Secret'
  cost          INT,                      -- NULL = variable / not applicable
  rules_text    TEXT NOT NULL,
  flavor_text   TEXT,                     -- ARG fragments go here
  rarity        TEXT NOT NULL DEFAULT 'common'
                  CHECK (rarity IN ('common','uncommon','rare','mythic','secret')),
  serial_scheme TEXT NOT NULL DEFAULT 'numbered'
                  CHECK (serial_scheme IN ('numbered','null','open')),
  version       INT NOT NULL DEFAULT 1,   -- errata bumps version, never rewrites
  supersedes_id UUID REFERENCES card_definitions(id),
  metadata      JSONB NOT NULL DEFAULT '{}',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (slug, version)
);

CREATE TABLE media_assets (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  definition_id UUID NOT NULL REFERENCES card_definitions(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL CHECK (kind IN ('art','model_3d','audio','video')),
  url           TEXT NOT NULL,
  mime_type     TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (definition_id, kind)
);

CREATE TABLE card_instances (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  definition_id   UUID NOT NULL REFERENCES card_definitions(id),
  serial          TEXT,                   -- '000/000', '042/500', NULL for open editions
  edition         TEXT NOT NULL DEFAULT 'first',
  condition       TEXT,                   -- physical only: 'mint', 'played', ...
  claim_code_hash TEXT UNIQUE,            -- hashed QR/NFC claim secret (physical)
  status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','stolen','destroyed')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- NOTE: Postgres treats NULLs as distinct in UNIQUE, so open-edition
  -- copies (serial IS NULL) never collide; they are told apart by id.
  UNIQUE (definition_id, serial, edition)
);
CREATE INDEX ON card_instances (definition_id);

-- ---------------- ownership (append-only) ----------------

CREATE TABLE ownership_ledger (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  instance_id    UUID NOT NULL REFERENCES card_instances(id),
  from_player_id UUID REFERENCES players(id),   -- NULL on mint
  to_player_id   UUID REFERENCES players(id),   -- NULL on burn
  transfer_type  TEXT NOT NULL
                   CHECK (transfer_type IN ('mint','burn','sale','trade','claim','bridge')),
  tx_ref         TEXT,                           -- chain tx hash or order id
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (from_player_id IS DISTINCT FROM to_player_id)
);
CREATE INDEX ON ownership_ledger (instance_id, created_at DESC);

-- Current owner, derived from the ledger. Never updated in place.
CREATE VIEW current_ownership AS
SELECT DISTINCT ON (instance_id)
  instance_id,
  to_player_id AS owner_id,
  created_at   AS acquired_at
FROM ownership_ledger
ORDER BY instance_id, created_at DESC;

-- ---------------- games ----------------

CREATE TABLE games (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug            TEXT NOT NULL UNIQUE,   -- 'arena', 'mythos', 'odyssey'
  name            TEXT NOT NULL,
  platform        TEXT NOT NULL,          -- 'python', 'html5', 'godot-unity'
  ruleset_version TEXT NOT NULL DEFAULT '1.0.0',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE game_card_profiles (
  definition_id UUID NOT NULL REFERENCES card_definitions(id),
  game_id       UUID NOT NULL REFERENCES games(id),
  cost_override INT,                      -- NULL = use definition cost
  power         INT,
  toughness     INT,
  is_legal      BOOLEAN NOT NULL DEFAULT TRUE,
  banned_reason TEXT,
  rules_patch   TEXT,                     -- game-specific errata text
  metadata      JSONB NOT NULL DEFAULT '{}',
  PRIMARY KEY (definition_id, game_id)
);
CREATE INDEX ON game_card_profiles (game_id);

-- What a player can actually field inside a given digital game.
CREATE TABLE entitlements (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_id   UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
  instance_id UUID NOT NULL REFERENCES card_instances(id),
  game_id     UUID NOT NULL REFERENCES games(id),
  granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at  TIMESTAMPTZ,
  UNIQUE (player_id, instance_id, game_id)
);
CREATE INDEX ON entitlements (player_id, game_id);

-- ---------------- cross-medium links ----------------

CREATE TABLE nft_tokens (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  instance_id      UUID NOT NULL UNIQUE REFERENCES card_instances(id),
  chain            TEXT NOT NULL,
  contract_address TEXT NOT NULL,
  token_id         TEXT NOT NULL,
  token_uri        TEXT,                   -- points at definition metadata (IPFS/Arweave)
  minted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (chain, contract_address, token_id)
);

CREATE TABLE physical_links (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  instance_id UUID NOT NULL UNIQUE REFERENCES card_instances(id),
  nfc_uid     TEXT UNIQUE,
  qr_payload  TEXT UNIQUE,                -- what the printed QR encodes
  linked_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Stolen/destroyed attestations. Anchoring the evidence hash on-chain is
-- the system's ONLY blockchain interaction (Phase 1). Wallets and
-- on-chain transfer sync are Phase 2.
CREATE TABLE proofs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  instance_id UUID NOT NULL REFERENCES card_instances(id),
  proof_type TEXT NOT NULL CHECK (proof_type IN ('stolen','destroyed')),
  evidence_hash TEXT NOT NULL,            -- SHA-256 of canonical proof JSON
  chain TEXT,                             -- chain used for anchoring
  tx_hash TEXT,                           -- anchoring transaction
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','anchored','failed')),
  reporter_player_id UUID REFERENCES players(id),
  anchored_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON proofs (instance_id);

-- ============================================================
-- Seed: CARDREALM issuer, "The Temp" (v1), the three games,
-- per-game profiles, and the 000/000 null-serial instance.
-- ============================================================

INSERT INTO issuers (name, slug) VALUES ('CARDREALM', 'cardrealm');

INSERT INTO card_definitions
  (issuer_id, slug, name, type_line, cost, rules_text, flavor_text,
   rarity, serial_scheme, version)
SELECT
  id, 'the-temp', 'The Temp', 'Creature · Secret', 9,
  'Indestructible. At the end of each turn, The Temp devours an opposing token and gains its power. Return it to your hand only by paying 3 sanity — the contract cannot be renewed forever.',
  'Its badge never worked. It never needed one. The null serial was never lost — it was waiting to be hired.',
  'secret', 'null', 1
FROM issuers WHERE slug = 'cardrealm';

INSERT INTO games (slug, name, platform) VALUES
  ('arena',   'Arena',   'python'),
  ('mythos',    'MYTHOS',    'html5'),
  ('odyssey', 'Odyssey', 'godot-unity');

INSERT INTO game_card_profiles
  (definition_id, game_id, cost_override, power, is_legal, banned_reason,
   rules_patch, metadata)
SELECT d.id, g.id, p.cost_override, p.power, p.is_legal, p.banned_reason,
       p.rules_patch, p.metadata
FROM card_definitions d
CROSS JOIN games g
JOIN (VALUES
  ('arena',   9,    9,    TRUE,  NULL::TEXT, NULL::TEXT, '{}'::JSONB),
  -- Real MYTHOS data for The Temp (id 14): cost 2 in-game vs 9 canon.
  ('mythos',  2,    2,    TRUE,  NULL::TEXT,
   'At the end of your turn, return The Temp to your hand unless you pay 1 sanity (contract renewal).',
   '{"flesh":2,"leash":1,"upkeep":1}'::JSONB),
  ('odyssey', NULL, NULL, FALSE, 'Devour mechanic not implemented in Odyssey ruleset v1',
   NULL::TEXT, '{}'::JSONB)
) AS p(game_slug, cost_override, power, is_legal, banned_reason, rules_patch, metadata)
  ON p.game_slug = g.slug
WHERE d.slug = 'the-temp' AND d.version = 1;

-- The null-serial instance shown in the card viewer.
INSERT INTO card_instances (definition_id, serial, edition)
SELECT id, '000/000', 'first'
FROM card_definitions WHERE slug = 'the-temp' AND version = 1;
