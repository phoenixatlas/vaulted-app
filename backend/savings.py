"""Illustrative saving vs a typical UK bank transfer.

Same assumption everywhere (website calculator, app quote, receipts):
£25 bank fee + 3% exchange-rate margin. Net of Vaulted's own service fee.
"""
from typing import Optional

BANK_FEE_GBP = 25.0
BANK_FX_MARGIN = 0.03
NOTE = (f"Illustrative: compared with a typical bank transfer charging a £{BANK_FEE_GBP:.0f} fee "
        f"and a {BANK_FX_MARGIN * 100:.0f}% exchange-rate margin. Real bank costs vary.")


def bank_saving(quote: dict) -> Optional[float]:
    """Saving in destination currency, or None when the comparison isn't fair (send ≤ bank fee)."""
    try:
        src = quote["source"]
        amt, amt_gbp, amt_usd = float(src["amount"]), float(src.get("amount_gbp") or 0), float(src["amount_usd"])
        fx, dest = float(quote["fx_rate"]), float(quote["destination"]["amount"])
        fee_usd = float((quote.get("fees") or {}).get("vaulted_service_usd") or 0)
    except (KeyError, TypeError, ValueError):
        return None
    if not (amt and amt_gbp and amt_usd and fx):
        return None
    bank_fee_src = BANK_FEE_GBP * (amt / amt_gbp)
    if amt <= bank_fee_src:
        return None
    bank_gets = (amt - bank_fee_src) * fx * (1 - BANK_FX_MARGIN)
    saving = dest - fee_usd * (dest / amt_usd) - bank_gets
    return round(saving, 2) if saving > 0 else None
