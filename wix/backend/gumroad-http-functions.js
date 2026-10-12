// CardRealm — Gumroad → Wix verification endpoint.
// Paste into Dev Mode as backend/http-functions.js (or merge the
// export into your existing http-functions.js).
//
// Gumroad Ping (sales) and membership resource subscriptions POST to:
//   https://<your-site>/_functions/gumroadPing?key=<GUMROAD_PING_SECRET>
// Set that URL in Gumroad (product Ping settings + membership
// webhooks). The key is a shared secret in the Wix Secrets Manager.
//
// Flow (design/gumroad-wix-verification.md):
//   1. Check the shared-secret key. A ping is never trusted alone.
//   2. Verify the event with the Gumroad API (one call), using
//      GUMROAD_ACCESS_TOKEN from Secrets Manager.
//   3. Create-or-match the Wix member by email.
//   4. syncMemberEntitlement() → the registry upserts the player and
//      grants/revokes membership entitlements in the same pass.
// Refunds/disputes take the revoke path. Anything this endpoint
// misses is caught by the twice-daily reconciliation Action
// (scripts/reconcile_gumroad.py).
//
// NOT YET TESTED in a real Wix editor — the member create/match step
// uses the Wix Members REST API; confirm field names on first run
// (see the TODO in createOrMatchMember).

import { ok, badRequest, forbidden, serverError } from 'wix-http-functions';
import { fetch } from 'wix-fetch';
import { getSecret } from 'wix-secrets-backend';
import { syncMemberEntitlement } from 'backend/cardrealm-auth';

// TODO(Joshua): real Gumroad product IDs → tier + games.
// Mirrored in scripts/reconcile_gumroad.py and firestore/data-model.md.
const PRODUCT_TIER_MAP = {
  // 'PRODUCT_ID': { tier: 'cultist', gameSlugs: ['mythos'] },
};

const GUMROAD_API = 'https://api.gumroad.com/v2';

export async function post_gumroadPing(request) {
  try {
    const expected = await getSecret('GUMROAD_PING_SECRET');
    if (!request.query || request.query.key !== expected) {
      return forbidden();
    }
    const form = new URLSearchParams(await request.body.text());
    const saleId = form.get('sale_id');
    const email = (form.get('email') || '').trim().toLowerCase();
    const productId = form.get('product_id');
    if (!email || !productId) {
      return badRequest('missing email or product_id');
    }
    const mapped = PRODUCT_TIER_MAP[productId];
    if (!mapped) {
      // Unknown product: acknowledge so Gumroad doesn't retry
      // forever, but grant nothing.
      console.warn('gumroadPing: unmapped product', productId);
      return ok();
    }

    // A ping can self-report a refund/dispute, but verify regardless.
    let revoke =
      form.get('refunded') === 'true' || form.get('disputed') === 'true';
    if (saleId) {
      const sale = await verifySale(saleId);
      if (!sale) {
        // Couldn't verify — 500 so Gumroad retries later.
        return serverError('verification failed');
      }
      if (sale.refunded || sale.disputed || sale.chargebacked) {
        revoke = true;
      }
      if ((sale.email || '').trim().toLowerCase() !== email) {
        return badRequest('email mismatch');
      }
    } else if (form.get('cancelled_at') || form.get('ended_at')) {
      revoke = true; // membership cancellation notice
    }

    const member = await createOrMatchMember(email, form.get('full_name'));
    if (!member) return serverError('member create/match failed');

    await syncMemberEntitlement(member, {
      tier: mapped.tier,
      gameSlugs: mapped.gameSlugs,
      sourceEventId: saleId || form.get('subscription_id') || undefined,
      revoke,
    });
    return ok();
  } catch (err) {
    console.error('gumroadPing failed', err);
    return serverError();
  }
}

async function verifySale(saleId) {
  const token = await getSecret('GUMROAD_ACCESS_TOKEN');
  const res = await fetch(`${GUMROAD_API}/sales/${saleId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data.success ? data.sale : null;
}

// Create-or-match a Wix member by email, via the Members REST API.
// Returns a member-shaped object ({ _id, loginEmail, profile }) that
// backend/cardrealm-auth understands.
// TODO(first run in the editor): confirm the query filter shape and
// the Create Member payload — the API may require a temporary
// password or send a set-password invite instead of a plain create.
async function createOrMatchMember(email, fullName) {
  const headers = {
    Authorization: await getSecret('WIX_API_KEY'),
    'wix-site-id': await getSecret('WIX_SITE_ID'),
    'Content-Type': 'application/json',
  };
  const queryRes = await fetch(
    'https://www.wixapis.com/members/v1/members/query',
    {
      method: 'POST',
      headers,
      body: JSON.stringify({ query: { filter: { loginEmail: email } } }),
    }
  );
  if (queryRes.ok) {
    const data = await queryRes.json();
    const found = (data.members || [])[0];
    if (found) return found;
  }
  const createRes = await fetch('https://www.wixapis.com/members/v1/members', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      member: {
        loginEmail: email,
        profile: { nickname: fullName || email },
      },
    }),
  });
  if (!createRes.ok) return null;
  const created = await createRes.json();
  return created.member || null;
}
