// CardRealm — Wix page code snippet (frontend). Paste into the
// member-area page (or masterPage.js) in Dev Mode.
//
// What it does: after a member is logged into Wix, ask the backend
// for a Firebase custom token and sign into Firebase with it — one
// login across the Wix site, the card viewer, and the games.
//
// The firebaseConfig values below are the STAGING project's web
// config. A Firebase web apiKey is a project identifier, not a
// secret — but the Firebase ADMIN key must never appear in frontend
// code. Fill the values in from Firebase console → cardrealm-staging
// → Project settings → Your apps → Web app.

import { getFirebaseToken } from 'backend/cardrealm-auth';
import { initializeApp } from 'firebase/app';
import { getAuth, signInWithCustomToken } from 'firebase/auth';

const firebaseConfig = {
  apiKey: 'TODO — cardrealm-staging web apiKey',
  authDomain: 'cardrealm-staging.firebaseapp.com',
  projectId: 'cardrealm-staging',
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

// Call on page load (member pages only). Returns the Firebase user
// or null when no Wix member is logged in.
export async function signIntoFirebase() {
  const token = await getFirebaseToken();
  if (!token) return null;
  const cred = await signInWithCustomToken(auth, token);
  return cred.user; // uid will be `wix_<memberId>`, matching players/{uid}
}
