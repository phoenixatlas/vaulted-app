import { Platform } from "react-native";

// Apple 3.1.1: digital subscriptions sold inside the iOS app must use Apple
// In-App Purchase. Vault Pro is billed via Stripe, so purchase entry points
// are hidden on iOS until StoreKit is wired up.
export const PRO_PURCHASE_ENABLED = Platform.OS !== "ios";
