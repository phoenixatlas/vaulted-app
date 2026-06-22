# Vaulted — Secure Crypto Wallet (PRD)

## Vision
A self-custody crypto wallet mobile app that combines crypto storage, fiat on/off-ramps, end-to-end encrypted peer chat, and built-in video calls — all behind one trusted brand. iOS-Native Clean design (moss/sage palette).

## MVP Scope (Implemented)
1. **Auth (JWT + bcrypt)**: register, login, /me, logout, token in SecureStore.
2. **Crypto self-custody wallet (simulated)**: BTC/ETH/USDC/SOL balances, hero card showing total USD + wallet address, send (debit balance + tx hash), receive (QR + address share).
3. **Fiat transfers (simulated)**: deposit (card/bank/Apple Pay) credits USDC 1:1; withdraw debits USDC. Ticket-style receipts with VLT-XXXX ID.
4. **Activity / transaction history**: unified list across send/receive/deposit/withdraw.
5. **Secure chat**: 3 seeded contacts, conversation list with E2E lock indicator, full thread view, polling refresh, auto-ack reply for demo.
6. **Video call (mocked UI)**: encrypted call screen with timer, mic/cam/end controls, PiP.
7. **Language selection**: EN / ES / FR / AR runtime switch via i18n context.
8. **Security settings**: biometric & multi-sig toggles persisted on user.

## Architecture
- Backend: FastAPI + Motor (MongoDB). All routes under `/api`.
- Frontend: Expo Router (SDK 54), 4-tab nav (Wallet / Chat / Activity / Settings).
- Auth: JWT (HS256, 7d) → SecureStore.
- i18n: in-memory dict + AsyncStorage persistence.

## Not in MVP (intentionally MOCKED)
- Real on-chain transactions (simulated; tx hashes are random hex).
- Real fiat payment processor (no Stripe/banking — simulated balance moves).
- Real WebRTC video call (screen is mocked UI with timer + controls).
- True E2E encryption of chat payloads (UI indicator only; messages stored plaintext server-side).
