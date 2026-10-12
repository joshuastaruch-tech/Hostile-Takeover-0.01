# Design Brief — Prequel 1: Dungeon Crawler Card Battler

*Working title TBD. HTML game. Canonically a prequel to MYTHOS; releasing after it.
Status: very early. Dictated by Joshua, 2026-10-10.*

## Elevator pitch

A retro, early-era card-battle dungeon crawler that starts normal — and then
the game itself starts breaking. The dungeon, the monsters, the UI, and the
player's own weapons all succumb to a Lovecraftian corruption leaking in from
a deck that doesn't belong in this game, in this time.

## Format & aesthetic

- HTML game, early-game-era presentation (retro dungeon crawler).
- Card battles as the core combat loop; party-based adventuring.

## Story beats (in order)

1. **The normal game.** Classic dungeon crawl: card battles, adventurer
   weapons, legendary weapons earned the hard way. Everything works as
   expected.
2. **The discovery.** The party finds the original digital deck.
3. **The wrongness.** The deck turns out to have real power against the
   dungeon's enemies — power it should not have. The game starts acting weird.
4. **The corruption spreads.** Glitches manifest. Monsters take on
   Lovecraftian corruption. The UI itself begins telling the player the game
   is breaking — the interface becomes a horror device, not just a frame.
5. **Disarmament.** Normal adventurer weapons stop working. The old toolkit
   is dead.
6. **Corrupted legendaries.** Legendary weapons from the pre-deck portion of
   the game begin to corrupt — and the corruption *grants strange new
   attributes*. Power at a price; the player's arsenal becomes alien.
7. **The Trader (before the fifth and final boss).** The party meets a
   strange entity named The Trader, who explains: the deck wasn't made for
   this game. It was *borrowed* — from the future — from something whispering
   in a nightmare.
8. **The fourth wall breaks.** After the party advances to the final level,
   The Trader addresses the *player*, not the party: we'll meet again soon.
   He warns that the final boss is corrupted and will only take real damage
   from something legendary that's been corrupted by "the dead but dreaming."
9. **The final boss.** Corrupted; conventional damage doesn't stick. Victory
   requires a corrupted legendary — the very thing the corruption gave you.

## Key entities

- **The Trader** — cross-game entity. Knows about the deck's true origin,
  breaks the fourth wall, promises to return ("we'll meet again soon").
  Prime candidate for a future card and for appearances in other games.
- **The whispering nightmare thing** — the deck's true source. "Dead but
  dreaming" reads as the Cthulhu-shaped hole at the center of the canon:
  that which waits dreaming, whispering forward through time.
- **The corrupted final boss** — damage-gated: only harmed by corrupted
  legendary gear. Forces the player to embrace the corruption to win.

## Systems

- **Card battles** — core combat, retro-styled.
- **Weapon corruption** — legendary weapons gain strange attributes as they
  corrupt. Design as a progression track: each legendary has a clean state
  and one or more corrupted states with new powers and costs.
- **Glitch UI** — the interface degrades deliberately as corruption spreads:
  visual artifacts, lying or frightened UI text, unreliable displays.
- **Five bosses**, escalating; the fifth is the corrupted finale.

## Design pillars

1. The game breaking *is* the story.
2. Power comes from corruption, never cleanly.
3. The horror is canonical — this all really happened before MYTHOS.
4. The Trader connects the games; the deck connects the timelines.

## Registry hooks (for later)

- **Completion unlock:** finishing this game + the platformer prequel grants
  the first post-Alpha card release (in-game entitlement + preorder
  reservation). Completion event → registry.
- **The Trader** is a natural future card definition (and a cross-game
  NPC/entity record).
- **Corrupted weapons** map cleanly onto card instances with modified
  attributes — the registry's `rules_patch` / per-instance state was built
  for exactly this.
- **Canon era:** pre-Alpha. Card definitions will want an era field
  (pre-Alpha / Alpha / post-Alpha) as the timeline grows.

## Open questions

- Title?
- What exactly are the "strange attributes" on corrupted legendaries —
  mechanical list per weapon?
- What is the "legendary corrupted by the dead but dreaming" — a specific
  weapon the player must have corrupted, or any sufficiently corrupted one?
- Does The Trader appear in the second prequel too, or only here and later?
- How is completion detected/sent to the registry (end-of-game event)?
