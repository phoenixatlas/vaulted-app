"""Pydantic request / response models for the Vaulted API.

Extracted from server.py during the P2 router-split refactor. Every model
lives here so routers can import them without pulling in server-level side
effects (mongo client, env config, Stripe SDK, etc.).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


# ---------------------------- Auth ---------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1, max_length=80)
    # Optional 8-char alphanumeric invite code. Case-insensitive.
    referred_by_code: Optional[str] = Field(default=None, max_length=16)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UpdateLanguageIn(BaseModel):
    language: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=6, max_length=128)


# ---------------------------- E2E keys -----------------------------------
class RegisterKeyIn(BaseModel):
    public_key: str  # base64 NaCl box public key


# ---------------------------- Wallet -------------------------------------
class SendCryptoIn(BaseModel):
    asset: str
    amount: float = Field(gt=0)
    to_address: str
    memo: Optional[str] = None


class SendUsdcIn(BaseModel):
    to_address: str
    amount_usdc: float = Field(gt=0)


class SendEvmUsdcIn(BaseModel):
    chain: str  # "polygon" | "base" | "arbitrum" | "sepolia"
    to_address: str
    amount_usdc: float = Field(gt=0)


class SendCoinIn(BaseModel):
    to_address: str
    amount: float = Field(gt=0)


class SendXlmIn(BaseModel):
    to_address: str
    amount: float = Field(gt=0)
    memo: Optional[str] = None


class SendXrpIn(BaseModel):
    to_address: str
    amount: float = Field(gt=0)
    memo: Optional[str] = None


class SendEthIn(BaseModel):
    to_address: str
    amount_eth: float = Field(gt=0)


# ---------------------------- Fiat / Stripe ------------------------------
class FiatTxIn(BaseModel):
    amount: float = Field(gt=0)
    currency: str = "USD"
    method: Literal["card", "bank", "applepay"] = "card"


class StripeDepositIn(BaseModel):
    amount_usd: float = Field(gt=0, le=10000)


class StripeSyncIn(BaseModel):
    session_id: str


# ---------------------------- Remit --------------------------------------
class RemitQuoteIn(BaseModel):
    source_fiat: str = Field(min_length=3, max_length=3)
    amount: float = Field(gt=0)
    destination_code: str = Field(min_length=2, max_length=2)


class RemitSendIn(BaseModel):
    source_fiat: str = Field(min_length=3, max_length=3)
    amount: float = Field(gt=0)
    destination_code: str = Field(min_length=2, max_length=2)
    recipient_address: str
    recipient_name: Optional[str] = None
    memo: Optional[str] = None


class RemitFundIn(BaseModel):
    """Fund a cross-border send with fiat (card / Apple Pay / bank transfer)
    via Stripe. Backend stores the intended remit in Checkout metadata; on
    successful payment (webhook or /stripe/sync poll) the on-chain leg is
    executed automatically.  Users who prefer to spend crypto keep using
    /remit/send unchanged."""
    source_fiat: str = Field(min_length=3, max_length=3)
    amount: float = Field(gt=0)
    destination_code: str = Field(min_length=2, max_length=2)
    recipient_address: str
    recipient_name: Optional[str] = None
    memo: Optional[str] = None
    payment_method: Literal["card", "apple_pay", "google_pay", "bank"] = "card"


# ---------------------------- Off-ramp -----------------------------------
class OfframpQuoteIn(BaseModel):
    """Ask Kotani for a live USDC->KES rate before initiating a payout."""
    amount_usd: float = Field(gt=0)
    to_currency: str = Field(default="KES", min_length=3, max_length=3)


class OfframpInitiateIn(BaseModel):
    """Auth'd, non-Stripe path: user has already deposited USDC and wants
    to push it straight to an M-Pesa recipient."""
    phone_number: str = Field(min_length=10, max_length=18)
    recipient_name: str = Field(min_length=1, max_length=80)
    amount_usd: float = Field(gt=0)
    country: str = Field(default="KE", min_length=2, max_length=2)


# ---------------------------- KYC / Admin --------------------------------
class KycSessionIn(BaseModel):
    """Optional body for /kyc/session.
    - force_new: cancels any existing session and creates a fresh one. Used by
      the frontend's "Start over" escape hatch when a user is stuck retrying
      the same failed document scan.
    """
    force_new: bool = False


class ManualEddApproveIn(BaseModel):
    """Admin-triggered Enhanced Due Diligence approval - used when Stripe
    Identity's automated face-match / doc-check algorithms can't verify a
    legitimate user (algorithm ceiling, ~3-5% of users). The admin has
    already reviewed the customer's docs manually per MLR 2017 Reg 33.

    Every field except user_email/user_id is required for audit compliance.
    """
    user_id: Optional[str] = None
    user_email: Optional[EmailStr] = None
    # Must match compliance.TIER_LIMITS keys exactly, otherwise get_user_tier()
    # falls back to DEFAULT_TIER ("unverified") and the approval has no visible
    # effect. `kyc_full` is the default for manual EDD (Enhanced Due Diligence).
    target_tier: Literal["kyc_lite", "kyc_full"] = "kyc_full"
    edd_reference: str = Field(min_length=6, max_length=64)  # ticket / doc-store ref
    edd_reason: str = Field(min_length=8, max_length=500)     # why manual approval was warranted
    documents_verified: list[str] = Field(default_factory=list)


class AdminScreenIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dob: Optional[str] = None       # ISO YYYY-MM-DD
    country: Optional[str] = None    # ISO alpha-2


# ---------------------------- Chat ---------------------------------------
class SendMessageIn(BaseModel):
    conversation_id: str
    text: str = Field(min_length=1, max_length=8000)
    nonce: Optional[str] = None  # base64 NaCl secretbox nonce when encrypted
    encrypted: bool = False


class SendChatCryptoIn(BaseModel):
    conversation_id: str
    amount_eth: float = Field(gt=0, le=1.0)
    to_contact_id: Optional[str] = None  # required for group chats; ignored for 1-on-1


class CreateGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    contact_ids: list[str] = Field(min_length=1, max_length=20)


class StartConversationIn(BaseModel):
    contact_id: str


# ---------------------------- Video calls --------------------------------
class CallRoomIn(BaseModel):
    conversation_id: Optional[str] = None


# ---------------------------- Multi-sig ----------------------------------
class CosignerInviteIn(BaseModel):
    email: EmailStr
    label: Optional[str] = None


class ApprovalActionIn(BaseModel):
    token: str
    decision: Literal["approve", "reject"]


# ---------------------------- Push notifications -------------------------
class RegisterPushBody(BaseModel):
    user_id: str
    platform: str
    device_token: str
