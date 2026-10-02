"""Unit tests for the hardened Kotani v3 webhook pipeline.

Covers:
  1. Canonical `sha256=<hex>` signature verification over `{event, data}`
  2. Raw-body signature fallback (older sandbox / direct callback)
  3. `classify_status` enum mapping
  4. `pick()` snake/camel helper
  5. `extract_mpesa_receipt` across the three Kotani field shapes

These are offline unit tests — no network, no running backend required.
Run with:
    cd /app/backend && python -m pytest tests/test_kotani_webhook_v3.py -v
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

import pytest

import kotani


SECRET = "unit_test_secret_abc123"


@pytest.fixture(autouse=True)
def _set_secret(monkeypatch):
    monkeypatch.setenv("KOTANI_WEBHOOK_SECRET", SECRET)
    # Make sure we don't accidentally hit live-mode gates.
    monkeypatch.setenv("KOTANI_API_KEY", "")
    yield


def _sign_canonical(event: str, data: dict, secret: str = SECRET) -> tuple[bytes, str]:
    envelope = {"event": event, "data": data}
    canonical = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
    # Server receives a slightly re-serialized body (with signature appended);
    # client always re-canonicalises before HMAC-ing.
    body = {"event": event, "data": data, "signature": f"sha256={sig}"}
    return json.dumps(body).encode("utf-8"), f"sha256={sig}"


class TestCanonicalSignature:
    def test_valid_canonical_signature_passes(self):
        body, header = _sign_canonical(
            "transaction.offramp.status.updated",
            {"referenceId": "ref1", "status": "SUCCESSFUL"},
        )
        assert kotani.verify_webhook_signature(body, header) is True

    def test_header_without_prefix_still_passes(self):
        body, header = _sign_canonical(
            "transaction.offramp.status.updated",
            {"referenceId": "ref1", "status": "SUCCESSFUL"},
        )
        bare = header.split("=", 1)[1]  # strip "sha256=" prefix
        assert kotani.verify_webhook_signature(body, bare) is True

    def test_tampered_body_fails(self):
        body, header = _sign_canonical(
            "transaction.offramp.status.updated",
            {"referenceId": "ref1", "status": "SUCCESSFUL"},
        )
        tampered = body.replace(b"ref1", b"ref2")
        assert kotani.verify_webhook_signature(tampered, header) is False

    def test_wrong_secret_fails(self):
        body, header = _sign_canonical(
            "transaction.offramp.status.updated",
            {"referenceId": "ref1", "status": "SUCCESSFUL"},
            secret="not_the_real_secret",
        )
        assert kotani.verify_webhook_signature(body, header) is False

    def test_no_secret_configured_short_circuits_true(self, monkeypatch):
        monkeypatch.setenv("KOTANI_WEBHOOK_SECRET", "")
        assert kotani.verify_webhook_signature(b'{"anything":true}', None) is True

    def test_missing_header_when_secret_set_fails(self):
        body = json.dumps({"event": "x", "data": {}}).encode()
        assert kotani.verify_webhook_signature(body, None) is False


class TestRawBodyFallback:
    """Direct-callback mode: body is the raw tx object, no `event` wrapper.
    Covers backwards-compat with the older sandbox + any Kotani deployment
    that still signs raw bytes."""

    def test_raw_body_hmac_accepted(self):
        body = json.dumps({"referenceId": "ref-raw", "status": "SUCCESSFUL"}).encode()
        sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        assert kotani.verify_webhook_signature(body, f"sha256={sig}") is True

    def test_raw_body_wrong_sig_rejected(self):
        body = json.dumps({"referenceId": "ref-raw", "status": "SUCCESSFUL"}).encode()
        assert kotani.verify_webhook_signature(body, "sha256=deadbeef") is False


class TestClassifyStatus:
    @pytest.mark.parametrize("inp,expected", [
        ("SUCCESSFUL", "settled"),
        ("Successful", "settled"),      # case-insensitive
        ("SUCCESS", "settled"),          # legacy mock
        ("COMPLETED", "settled"),
        ("FAILED", "failed"),
        ("ERROR", "failed"),
        ("CANCELLED", "failed"),
        ("REFUNDED", "refunded"),
        ("REVERSED", "refunded"),
        ("INVOICE_NEEDED", "refund_pending"),
        ("PENDING", "processing"),
        ("", "processing"),
        (None, "processing"),
    ])
    def test_mapping(self, inp, expected):
        assert kotani.classify_status(inp) == expected


class TestPick:
    def test_snake_case_read(self):
        data = {"reference_id": "abc", "customer_key": "x"}
        assert kotani.pick(data, "reference_id") == "abc"
        assert kotani.pick(data, "customer_key") == "x"

    def test_camel_case_fallback(self):
        data = {"referenceId": "abc", "customerKey": "x"}
        assert kotani.pick(data, "reference_id") == "abc"
        assert kotani.pick(data, "customer_key") == "x"

    def test_default_when_missing(self):
        assert kotani.pick({"foo": 1}, "reference_id", default="MISSING") == "MISSING"


class TestExtractMpesaReceipt:
    def test_camel_telco_id(self):
        # Offramp/withdrawal shape per Kotani v3 docs.
        data = {"telcoId": "MPESA-ABC123"}
        assert kotani.extract_mpesa_receipt(data) == "MPESA-ABC123"

    def test_snake_telco_id(self):
        # Deposit shape per Kotani v3 docs.
        data = {"telco_id": "MPESA-ABC123"}
        assert kotani.extract_mpesa_receipt(data) == "MPESA-ABC123"

    def test_legacy_receipt_object(self):
        # Older sandbox builds — our mock also returns this shape.
        data = {"receipt": {"mpesaReceipt": "MPESA-LEGACY-9"}}
        assert kotani.extract_mpesa_receipt(data) == "MPESA-LEGACY-9"

    def test_none_when_missing(self):
        assert kotani.extract_mpesa_receipt({}) is None

    def test_handles_non_dict(self):
        assert kotani.extract_mpesa_receipt(None) is None
        assert kotani.extract_mpesa_receipt("string") is None
