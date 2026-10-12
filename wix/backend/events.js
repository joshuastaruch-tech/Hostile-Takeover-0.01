// CardRealm — Wix Velo BACKEND events (paste into Dev Mode as
// backend/events.js). Keeps registry players/{uid} docs in sync when
// members join or change their profile on the Wix site.
//
// DRAFT — read before enabling:
// mint_auth_token has the `purpose === 'sync'` branch (added
// 2026-10-12): these handlers upsert only, no token is minted.
// Still draft until exercised once in the staging site's Dev Mode —
// enable after that test passes.

import { syncMember } from 'backend/cardrealm-auth';

export function wixMembers_onMemberCreated(event) {
  return syncMember(event.entity).catch((err) =>
    console.error('CardRealm member-created sync failed', err)
  );
}

export function wixMembers_onMemberUpdated(event) {
  return syncMember(event.entity).catch((err) =>
    console.error('CardRealm member-updated sync failed', err)
  );
}
