/**
 * Stripe Identity `last_error.code` → friendly UX mapping.
 *
 * Stripe returns machine codes like `document_expired` or `selfie_face_mismatch`;
 * users need a plain-English reason + a concrete "do this next" tip.
 *
 * Reference: https://stripe.com/docs/identity/verification-checks?type=document
 */

export type KycErrorInfo = {
  title: string;
  reason: string;
  tip: string;
  fatal?: boolean;   // when true, retrying with same doc won't help → offer "start over"
};

const MAP: Record<string, KycErrorInfo> = {
  // ---------- Document capture failures ----------
  document_expired: {
    title: "Document expired",
    reason: "The ID you uploaded has passed its expiry date.",
    tip: "Please use a current, in-date passport, driving licence, or national ID card.",
    fatal: true,
  },
  document_type_not_supported: {
    title: "Document type not supported",
    reason: "The document you uploaded isn't one we can accept.",
    tip: "Try a passport, driving licence, or government-issued national ID card.",
    fatal: true,
  },
  document_unverified_other: {
    title: "We couldn't read your document",
    reason: "The photo of your ID was too blurry, cropped, or too dark to verify.",
    tip: "Retake in bright, even lighting. Lay the document flat, fit all four corners in frame, and hold steady.",
  },
  document_missing_front: {
    title: "Front of document missing",
    reason: "We didn't receive a clear photo of the front side of your ID.",
    tip: "Make sure the side with your photo and details is fully visible in the frame.",
  },
  document_missing_back: {
    title: "Back of document missing",
    reason: "Your ID card needs both sides — we didn't get the back.",
    tip: "Flip the card over and capture the back when prompted.",
  },
  under_supported_age: {
    title: "Age restriction",
    reason: "You must be 18 or older to use Vaulted for cross-border remittance.",
    tip: "Contact support@phoenix-atlas.com if you believe this is an error.",
    fatal: true,
  },
  country_not_supported: {
    title: "Country not supported",
    reason: "The country your document was issued in isn't currently supported by our identity provider.",
    tip: "Contact support@phoenix-atlas.com and we'll look into a manual verification path.",
    fatal: true,
  },

  // ---------- Selfie/liveness failures ----------
  selfie_document_missing_photo: {
    title: "Selfie didn't match document",
    reason: "We couldn't find a photo on the document to compare against your selfie.",
    tip: "Make sure the photo page (with your face) is clearly visible when you scan.",
  },
  selfie_face_mismatch: {
    title: "Selfie didn't match your ID photo",
    reason: "The selfie we took didn't match the photo on your document confidently enough.",
    tip: "Remove hats, glasses, and masks. Look straight at the camera in good lighting.",
  },
  selfie_manipulated: {
    title: "Selfie flagged as manipulated",
    reason: "Your selfie appears to have been altered or wasn't captured live.",
    tip: "Do the selfie in real time, in your own lighting. Don't use a photo of a photo.",
  },
  selfie_unverified_other: {
    title: "Selfie verification failed",
    reason: "We couldn't verify your selfie against the document.",
    tip: "Retake in bright lighting, face the camera directly, and follow the on-screen prompts.",
  },

  // ---------- Personal-details mismatches ----------
  id_number_mismatch: {
    title: "ID number didn't match",
    reason: "The ID number on your document doesn't match what you entered.",
    tip: "Double-check the number and try again — even a single character can cause a mismatch.",
  },
  id_number_insufficient_document_data: {
    title: "ID number couldn't be read",
    reason: "Stripe couldn't find or read the ID number on your document.",
    tip: "Retake the photo with the ID number area clearly visible and in focus.",
  },
  id_number_unverified_other: {
    title: "ID number couldn't be verified",
    reason: "We couldn't verify the ID number on your document.",
    tip: "Retake the document photo in better lighting, or try a different form of ID.",
  },
  dob_mismatch: {
    title: "Date of birth didn't match",
    reason: "The date of birth on your document doesn't match what you entered.",
    tip: "Correct the date and try again.",
  },
  dob_unverified_other: {
    title: "Date of birth couldn't be verified",
    reason: "We couldn't confirm your date of birth from the document.",
    tip: "Retake the photo so the date of birth is clearly readable.",
  },
  name_mismatch: {
    title: "Name didn't match",
    reason: "The name on your document doesn't match the name on your Vaulted account.",
    tip: "Make sure your Vaulted account uses your legal name exactly as printed on your ID.",
  },
  name_unverified_other: {
    title: "Name couldn't be verified",
    reason: "We couldn't confirm the name on your document.",
    tip: "Retake the photo so the name line is fully visible and in focus.",
  },
  address_mismatch: {
    title: "Address didn't match",
    reason: "The address on your document doesn't match your provided address.",
    tip: "Update your Vaulted account address to match the document, or use ID with the correct address.",
  },
  address_unverified_other: {
    title: "Address couldn't be verified",
    reason: "We couldn't confirm the address on your document.",
    tip: "Retake in better lighting or use a document with a clear address block.",
  },

  // ---------- Session-level failures ----------
  consent_declined: {
    title: "You declined consent",
    reason: "You declined Stripe's terms during verification — we can't proceed without them.",
    tip: "Tap 'Start over' and accept the terms when prompted.",
    fatal: true,
  },
  device_not_supported: {
    title: "Device not supported",
    reason: "Your current device doesn't support secure document capture.",
    tip: "Please retry on a phone or tablet with a working camera.",
    fatal: true,
  },
  abandoned: {
    title: "Verification was abandoned",
    reason: "You closed the verification before completing it.",
    tip: "Tap 'Try again' to resume, or 'Start over' for a fresh session.",
  },
  email_verification_declined: {
    title: "Email verification declined",
    reason: "The email link wasn't confirmed.",
    tip: "Tap 'Try again' and complete the email step.",
  },
  phone_verification_declined: {
    title: "Phone verification declined",
    reason: "The SMS code wasn't confirmed.",
    tip: "Tap 'Try again' and complete the SMS step.",
  },
};

const GENERIC: KycErrorInfo = {
  title: "Verification needs another attempt",
  reason: "We couldn't confirm your identity from the last attempt.",
  tip: "This can happen because of your document photo OR because your selfie didn't match the photo on your ID. Try the tips below — pay special attention to the selfie tips if your document is more than a few years old.",
};

/** Selfie-specific "what to do next" — surfaces when we detect the
 * failure was at the face-match step (e.g. selfie_face_mismatch,
 * selfie_unverified_other) rather than a document quality issue. */
export const SELFIE_TIPS: string[] = [
  "Match how you look on your ID photo — remove glasses if you didn't wear them, or wear them if you did",
  "Match your facial hair to the ID photo (shave/regrow if significantly different)",
  "No hat, hood, or head covering — bare head unless it's on your ID",
  "Look directly at the camera at eye level — don't hold the phone below your chin",
  "Even light on your face (not the document) — window in front of you, no backlight",
  "Neutral expression, mouth closed, both eyes visible",
];

export function kycErrorInfo(code: string | null | undefined, fallbackReason?: string | null): KycErrorInfo {
  if (!code) return { ...GENERIC, reason: fallbackReason || GENERIC.reason };
  const info = MAP[code];
  if (!info) return { ...GENERIC, reason: fallbackReason || GENERIC.reason };
  return info;
}

/** Concrete photo-capture tips shown as a checklist under the error. */
export const PHOTO_TIPS: string[] = [
  "Use bright, even lighting — avoid glare and shadows",
  "Lay the document flat on a dark background",
  "Fit all four corners of the ID in the frame",
  "Hold the phone steady until the shutter fires",
  "Remove any card holder or plastic sleeve",
];
