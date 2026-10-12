/* MYTHOS x Card Registry overlay.
 *
 * The game ships card data embedded in MYTHOS_DATA.cards (offline-first).
 * When Firestore is reachable, this module overlays registry profiles
 * (cardDefinitions/{slug}__v1/gameProfiles/mythos) onto those cards, so
 * balance changes, errata and legality updates land without redeploying
 * the game. Reads are public -- no secrets. Ownership checks stay
 * server-side (see sdks/web/server-proxy.example.js).
 *
 * Usage (after firebase.js has initialized):
 *   MYTHOS_REGISTRY.sync().then(function (online) {
 *     var cards = MYTHOS_REGISTRY.applyAll(window.MYTHOS_DATA.cards);
 *     startGame(cards);
 *   });
 */
(function (global) {
  'use strict';

  var GAME_SLUG = 'mythos';

  function slugify(name) {
    return String(name).toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .replace(/-+/g, '-');
  }

  var profiles = {};  // slug -> gameProfiles/mythos doc
  var ready = false;

  function getDb() {
    try {
      if (typeof firebase !== 'undefined' && firebase.firestore) {
        return firebase.firestore();
      }
    } catch (e) { /* offline */ }
    return null;
  }

  // One collectionGroup query pulls every mythos profile at once.
  function sync() {
    var db = getDb();
    if (!db || !firebase.firestore.FieldPath) return Promise.resolve(false);
    return db.collectionGroup('gameProfiles')
      .where(firebase.firestore.FieldPath.documentId(), '==', GAME_SLUG)
      .get()
      .then(function (snap) {
        snap.forEach(function (doc) {
          // doc path: cardDefinitions/{slug}__v1/gameProfiles/mythos
          var defId = doc.ref.parent.parent.id;
          profiles[defId.replace(/__v\d+$/, '')] = doc.data();
        });
        ready = true;
        return true;
      })
      .catch(function () { return false; });  // offline: keep embedded data
  }

  function profileFor(card) {
    return profiles[slugify(card.name)] || null;
  }

  // Card with registry overrides applied. Never mutates the original.
  function withRegistry(card) {
    var p = profileFor(card);
    if (!p) return card;
    var out = Object.assign({}, card);
    if (p.costOverride != null) out.cost = p.costOverride;
    if (p.stats) {
      Object.keys(p.stats).forEach(function (k) {
        if (p.stats[k] != null) out[k] = p.stats[k];
      });
    }
    if (p.rulesPatch) out.rules = p.rulesPatch;
    out._registry = {
      legal: p.isLegal !== false,
      bannedReason: p.bannedReason || null
    };
    return out;
  }

  function isLegal(card) {
    var p = profileFor(card);
    return !p || p.isLegal !== false;
  }

  // Local legality sanity check. Authoritative ownership still server-side.
  function validateDeckLocal(cards) {
    var banned = cards.filter(function (c) { return !isLegal(c); })
                      .map(function (c) { return c.name; });
    return { legal: banned.length === 0, banned: banned };
  }

  global.MYTHOS_REGISTRY = {
    gameSlug: GAME_SLUG,
    sync: sync,
    isReady: function () { return ready; },
    profileFor: profileFor,
    withRegistry: withRegistry,
    isLegal: isLegal,
    validateDeckLocal: validateDeckLocal,
    // MYTHOS_DATA.cards.map(MYTHOS_REGISTRY.withRegistry)
    applyAll: function (cards) { return cards.map(withRegistry); }
  };
})(typeof window !== 'undefined' ? window : global);
