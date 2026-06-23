// Client-side end-to-end encryption helpers (NaCl secretbox).
// The user's secret symmetric key is generated on first login, stored locally,
// and never leaves the device. Outgoing messages are encrypted with a fresh
// random nonce; ciphertext + nonce are sent to the server in base64.
import nacl from "tweetnacl";
import naclUtil from "tweetnacl-util";
import { storage } from "@/src/utils/storage";

const SECRET_KEY = "vaulted_e2e_secret_b64";

function toB64(bytes: Uint8Array): string {
  return naclUtil.encodeBase64(bytes);
}
function fromB64(b64: string): Uint8Array {
  return naclUtil.decodeBase64(b64);
}

export async function ensureSecretKey(): Promise<Uint8Array> {
  const existing = await storage.secureGet<string>(SECRET_KEY, "");
  if (existing) {
    try {
      const bytes = fromB64(existing);
      if (bytes.length === nacl.secretbox.keyLength) return bytes;
    } catch {
      /* fall through */
    }
  }
  const key = nacl.randomBytes(nacl.secretbox.keyLength);
  await storage.secureSet(SECRET_KEY, toB64(key));
  return key;
}

export async function getPublicFingerprint(): Promise<string> {
  // For UI display only — first 8 hex chars of SHA-like hash (use first bytes of key as proxy).
  const k = await ensureSecretKey();
  return Array.from(k.slice(0, 4))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function encryptText(plain: string): Promise<{ ciphertext: string; nonce: string }> {
  const key = await ensureSecretKey();
  const nonce = nacl.randomBytes(nacl.secretbox.nonceLength);
  const box = nacl.secretbox(naclUtil.decodeUTF8(plain), nonce, key);
  return { ciphertext: toB64(box), nonce: toB64(nonce) };
}

export async function decryptText(ciphertextB64: string, nonceB64: string): Promise<string | null> {
  try {
    const key = await ensureSecretKey();
    const box = fromB64(ciphertextB64);
    const nonce = fromB64(nonceB64);
    const plain = nacl.secretbox.open(box, nonce, key);
    if (!plain) return null;
    return naclUtil.encodeUTF8(plain);
  } catch {
    return null;
  }
}

export async function resetSecretKey() {
  await storage.secureRemove(SECRET_KEY);
}
