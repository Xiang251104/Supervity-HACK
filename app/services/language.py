# app/services/language.py
"""Plain language for text the backend composes.

AI Insights sentences reach the same non-technical reader as the frontend, so
reason codes and policy keys are translated before they land in a title or
body. This mirrors frontend/src/lib/ap-language.ts — if a label changes in one
place, change it in the other.
"""

from __future__ import annotations

REASON_LABELS: dict[str, str] = {
    "BEC_SUSPECTED": "possible payment-redirect fraud",
    "BANK_MISMATCH": "bank account not matching vendor records",
    "BANK_ACCOUNT_UNKNOWN": "bank account not on file",
    "BANK_CHANGE_UNVERIFIED": "unverified recent bank change",
    "VENDOR_BLOCKED": "blocked vendor",
    "VENDOR_DELETED": "vendor flagged for deletion",
    "VENDOR_MASTER_DUPLICATE": "duplicate vendor master records",
    "DUP_LATER_COPY": "duplicate of an invoice already received",
    "NEAR_DUP_SUSPECT": "suspected copy of another invoice",
    "PO_VENDOR_MISMATCH": "purchase order belonging to a different vendor",
    "PO_CURRENCY_MISMATCH": "currency differing from the purchase order",
    "PO_LINE_NO_MATCH": "amount not matching any PO line",
    "PO_LINE_AMBIGUOUS": "amount matching more than one PO line",
    "PO_OUT_OF_VALIDITY": "invoice dated outside the PO's validity",
    "RETRO_PO": "purchase order raised after the invoice",
    "ENTITY_MISMATCH": "billing to the wrong company entity",
    "RECEIPT_VARIANCE": "goods receipt not covering the invoice",
    "RECEIPT_MISSING": "no goods receipt recorded",
    "RECEIPT_PARTIAL": "goods only partly received",
    "GR_EXEMPT_FRAMEWORK": "framework order exempt from receipt",
    "LOW_CONFIDENCE": "hard-to-read invoice",
    "DATE_AMBIGUOUS": "ambiguous invoice date",
    "MISSING_INPUT": "missing key information",
    "CREDIT_MEMO": "credit note",
    "NON_PO_APPROVAL": "spend without a purchase order",
    "GL_CODING_REQUIRED": "missing ledger account",
    "DOA_BAND_NOT_FOUND": "no approver band covering the amount",
    "HIGH_VALUE": "high-value invoice",
}

# Phrased to read inside a sentence: "The <name> rule affected 7 invoices."
POLICY_NAMES: dict[str, str] = {
    "PRICE-TOLERANCE": "price tolerance",
    "BANK-CHANGE-FREEZE": "bank-change freeze",
    "DOA-BAND": "auto-pay limit",
    "GR-POLICY": "goods-receipt requirement",
    "RETRO-PO": "retroactive-PO handling",
    "MIN-CONFIDENCE": "minimum reading confidence",
    "AS-OF-DATE": "operational as-of date",
    "HIGH-VALUE-THRESHOLD": "high-value threshold",
    "NEAR-DUP-TOLERANCE": "near-duplicate tolerance",
    "DEFAULT-KOSTL": "default cost centre",
}


def reason_label(code: str) -> str:
    """A phrase for a reason code, falling back to the code itself."""
    return REASON_LABELS.get(code, code.replace("_", " ").lower())


def policy_name(key: str) -> str:
    """A phrase for a policy key, falling back to the key itself."""
    return POLICY_NAMES.get(key, key)
