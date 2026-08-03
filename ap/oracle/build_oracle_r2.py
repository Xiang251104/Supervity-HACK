r"""EXPECTED_ORACLE_R2 — independently computed answer key for the 450-invoice Round 2 pack.

This mirrors the five Operator specs in round2/planning/DELIVERY_PLAN_R2.md (Part B) exactly:
same reason codes, same statuses, same verdict precedence, same conservative money-protected
rule. Diff Auto's output against this to catch wrong verdicts.

The organizer dataset is NOT committed to this repository — it may not be redistributed.
Point this script at your own copy of the Round 2 csv folder:

    set AP_DATASET_DIR=C:\path\to\csv        (Windows)
    export AP_DATASET_DIR=/path/to/csv       (macOS/Linux)
    python build_oracle_r2.py

or pass it as the first argument:

    python build_oracle_r2.py /path/to/csv

Out:  EXPECTED_ORACLE_R2.csv  (+ a summary printed to stdout)
"""
from __future__ import annotations

import csv
import os
import re
import sys
from collections import defaultdict, Counter
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))


def _dataset_dir() -> str:
    """Locate the Round 2 csv folder. Fail loudly rather than half-running."""
    candidates = [
        sys.argv[1] if len(sys.argv) > 1 else None,
        os.getenv("AP_DATASET_DIR"),
        os.path.normpath(os.path.join(HERE, "..", "..", "dataset", "csv")),
    ]
    for c in candidates:
        if c and os.path.isdir(c) and os.path.isfile(os.path.join(c, "RBKP_Invoice.csv")):
            return c
    raise SystemExit(
        "Could not find the Round 2 dataset.\n"
        "The organizer pack is not committed to this repo (it may not be redistributed).\n"
        "Point this script at your own copy of the csv folder, e.g.:\n"
        "    python build_oracle_r2.py /path/to/csv\n"
        "or set AP_DATASET_DIR. The folder must contain RBKP_Invoice.csv."
    )


SRC = _dataset_dir()

# --- the policy snapshot the oracle assumes (mirror of policy defaults) -------
POLICY = {
    "policy_version": "oracle-1",
    "as_of_date": datetime(2026, 7, 15),
    "price_tolerance_pct": 2.0,
    "gr_policy": "fo_aware",          # overridden per-run below
    "bank_change_freeze_days": 30,
    "high_value_threshold": 500000.0,
    "min_confidence": 0.70,
    "auto_pay_limit": 5000.0,
    "near_dup_amount_tolerance_pct": 0.1,
    "default_kostl": "CC100",
    # A retroactive PO (invoice predates the PO) or an invoice before the PO validity
    # window is a process-control issue, not a payment risk. Default is to record it and
    # keep paying; a controller can tighten it to "review" in the Policies UI.
    "retro_po_policy": "advisory",   # "advisory" | "review"
}

FAIL_CODES = {
    "DUP_LATER_COPY", "PO_VENDOR_MISMATCH", "PO_CURRENCY_MISMATCH", "PO_LINE_NO_MATCH",
    "VENDOR_BLOCKED", "VENDOR_DELETED", "BEC_SUSPECTED", "ENTITY_MISMATCH",
}


def load(name):
    with open(os.path.join(SRC, name + ".csv"), newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def amt(s):
    """Operator 1 step 3 — deterministic amount parsing."""
    s = (s or "").strip()
    if not s:
        return None
    neg = s.startswith("-")
    s = s.lstrip("-")
    if "," in s and "." in s:            # 330,252.07
        s = s.replace(",", "")
    elif re.fullmatch(r"\d+,\d{2}", s):  # 327845,70
        s = s.replace(",", ".")
    else:                                # 1,234
        s = s.replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse_date(s):
    """Operator 1 step 4. Returns (datetime|None, code|None)."""
    s = (s or "").strip()
    if not s:
        return None, "DATE_MISSING"
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if d <= 12 and mo <= 12:
            return None, "DATE_AMBIGUOUS"      # never guess
        if d > 12:
            return datetime(y, mo, d), None
        return None, "DATE_AMBIGUOUS"
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%b %d %Y"):
        try:
            return datetime.strptime(s[:19] if f.startswith("%Y") else s, f), None
        except ValueError:
            pass
    return None, "DATE_MISSING"


def norm_ref(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").strip().upper()).replace("O", "0")


def domain(email):
    e = (email or "").strip().lower()
    return e.split("@")[-1] if "@" in e else ""


# --- load ---------------------------------------------------------------------
inv = load("RBKP_Invoice")
ven = load("LFA1_Vendor_Master")
ekko = load("EKKO_PO_Header")
ekpo = load("EKPO_PO_Item")
mseg = load("MSEG_Goods_Receipt")
doa = load("DOA_Matrix")
cc = load("Company_Codes")
fxr = load("FX_Rates")
bank = load("Bank_Master")
emh = load("Email_Headers")
gl = load("SKA1_GL_Master")

ekko_by = {r["EBELN"].strip(): r for r in ekko}
lines = defaultdict(list)
for r in ekpo:
    lines[r["EBELN"].strip()].append(r)

gr_qty = defaultdict(float)
for r in mseg:
    q = amt(r["MENGE"]) or 0.0
    sign = -1 if (r["BWART"].strip() == "102" or r["SHKZG"].strip().upper() == "H") else 1
    gr_qty[(r["EBELN"].strip(), r["EBELP"].strip())] += sign * q

ven_by = defaultdict(list)
for r in ven:
    ven_by[r["LIFNR"].strip()].append(r)

bank_by = defaultdict(list)
for r in bank:
    bank_by[r["LIFNR"].strip()].append(r)

emh_by = defaultdict(list)
for r in emh:
    emh_by[r["LIFNR"].strip()].append(r)

cc_by = {r["BUKRS"].strip(): r for r in cc}
gl_by = {r["SAKNR"].strip(): r for r in gl}

fx_by = defaultdict(list)
for r in fxr:
    d, _ = parse_date(r["GDATU"])
    if d:
        fx_by[(r["FCURR"].strip(), r["TCURR"].strip())].append((d, amt(r["UKURS"])))
for k in fx_by:
    fx_by[k].sort()

# invoice population per vendor, for duplicate screening
pop_by_vendor = defaultdict(list)
for r in inv:
    pop_by_vendor[r["LIFNR"].strip().upper()].append(r)


def canonical(r):
    """Operator 1."""
    codes, status = [], "PASS"
    a = amt(r["WRBTR"])
    bldat, dcode = parse_date(r["BLDAT"])
    if a is None:
        return None, "FAIL", ["AMOUNT_UNPARSEABLE"]
    if dcode:
        codes.append(dcode)
        status = "REVIEW"
    conf = r["CONFIDENCE"].strip()
    if conf and float(conf) < POLICY["min_confidence"]:
        codes.append("LOW_CONFIDENCE")
        status = "REVIEW"
    if a < 0:
        codes.append("CREDIT_MEMO")
        status = "REVIEW"
    ci = {
        "belnr": r["BELNR"].strip(), "lifnr": r["LIFNR"].strip().upper(),
        "xblnr": r["XBLNR"].strip().upper(), "ebeln": r["EBELN"].strip().upper(),
        "waers": r["WAERS"].strip().upper(), "amount": a, "bldat": bldat,
        "bank_on_inv": r["BANK_ON_INV"].strip(), "bukrs_on_inv": r["BUKRS_ON_INV"].strip(),
        "gl_code": r["GL_CODE"].strip(), "source_channel": r["SOURCE_CHANNEL"].strip(),
        "is_po": bool(r["EBELN"].strip()),
        "fingerprint": f"{r['LIFNR'].strip().upper()}|{r['XBLNR'].strip().upper()}|"
                       f"{r['WAERS'].strip().upper()}|{round(a, 2)}",
        "near_key": f"{r['LIFNR'].strip().upper()}|{norm_ref(r['XBLNR'])}",
    }
    return ci, status, codes


def op_duplicate(ci):
    """Operator 2."""
    pop = pop_by_vendor[ci["lifnr"]]
    same_fp = []
    for o in pop:
        oa = amt(o["WRBTR"])
        if oa is None:
            continue
        fp = (f"{o['LIFNR'].strip().upper()}|{o['XBLNR'].strip().upper()}|"
              f"{o['WAERS'].strip().upper()}|{round(oa, 2)}")
        if fp == ci["fingerprint"]:
            same_fp.append(o)
    if len(same_fp) > 1:
        def key(o):
            d, _ = parse_date(o["BLDAT"])
            return (d or datetime.max, o["BELNR"].strip())
        primary = sorted(same_fp, key=key)[0]
        if primary["BELNR"].strip() != ci["belnr"]:
            return "FAIL", ["DUP_LATER_COPY"], abs(ci["amount"])
    tol = POLICY["near_dup_amount_tolerance_pct"] / 100.0
    for o in pop:
        oa = amt(o["WRBTR"])
        if oa is None or o["BELNR"].strip() == ci["belnr"]:
            continue
        okey = f"{o['LIFNR'].strip().upper()}|{norm_ref(o['XBLNR'])}"
        ofp = (f"{o['LIFNR'].strip().upper()}|{o['XBLNR'].strip().upper()}|"
               f"{o['WAERS'].strip().upper()}|{round(oa, 2)}")
        if okey == ci["near_key"] and ofp != ci["fingerprint"]:
            bigger = max(abs(oa), abs(ci["amount"])) or 1
            if abs(abs(oa) - abs(ci["amount"])) <= bigger * tol:
                return "REVIEW", ["NEAR_DUP_SUSPECT"], abs(ci["amount"])
    return "PASS", [], 0.0


def op_three_way(ci, gr_policy):
    """Operator 3."""
    if not ci["is_po"]:
        return "NOT_APPLICABLE", [], 0.0
    h = ekko_by.get(ci["ebeln"])
    if h is None:
        return "REVIEW", ["PO_NOT_FOUND"], abs(ci["amount"])
    codes, status, protected = [], "PASS", 0.0
    if ci["lifnr"] != h["LIFNR"].strip().upper():
        return "FAIL", ["PO_VENDOR_MISMATCH"], abs(ci["amount"])
    if ci["waers"] != h["WAERS"].strip().upper():
        return "FAIL", ["PO_CURRENCY_MISMATCH"], abs(ci["amount"])
    aedat, _ = parse_date(h["AEDAT"])
    kdatb, _ = parse_date(h["KDATB"])
    date_warn = POLICY["retro_po_policy"] == "review"
    if ci["bldat"] and aedat and ci["bldat"] < aedat:
        codes.append("RETRO_PO")
        if date_warn:
            status = "REVIEW"
    if ci["bldat"] and kdatb and ci["bldat"] < kdatb:
        codes.append("PO_OUT_OF_VALIDITY")
        if date_warn:
            status = "REVIEW"

    tol = POLICY["price_tolerance_pct"] / 100.0
    cands = [l for l in lines.get(ci["ebeln"], [])
             if (amt(l["NETWR"]) or 0) > 0
             and abs(ci["amount"] - amt(l["NETWR"])) <= amt(l["NETWR"]) * tol]
    if len(cands) == 0:
        closest = min((l for l in lines.get(ci["ebeln"], []) if (amt(l["NETWR"]) or 0) > 0),
                      key=lambda l: abs(ci["amount"] - amt(l["NETWR"])), default=None)
        excess = 0.0
        if closest is not None:
            excess = max(0.0, ci["amount"] - amt(closest["NETWR"]) * (1 + tol))
        return "FAIL", codes + ["PO_LINE_NO_MATCH"], excess
    if len(cands) > 1:
        return "REVIEW", codes + ["PO_LINE_AMBIGUOUS"], 0.0

    l = cands[0]
    ordered = amt(l["MENGE"]) or 0.0
    recv = gr_qty.get((ci["ebeln"], l["EBELP"].strip()), 0.0)
    under = (amt(l["UNTTO"]) or 0.0) / 100.0
    if recv <= 0:
        if gr_policy == "fo_aware" and h["BSART"].strip() == "FO":
            codes.append("GR_EXEMPT_FRAMEWORK")
        else:
            codes.append("RECEIPT_MISSING"); status = "REVIEW"
    elif recv < ordered * (1 - under):
        codes.append("RECEIPT_PARTIAL"); status = "REVIEW"
        protected = abs(ci["amount"]) * (ordered - recv) / ordered if ordered else 0.0
    return status, codes, protected


def op_bank(ci):
    """Operator 4."""
    codes, status, protected = [], "PASS", 0.0
    vms = ven_by.get(ci["lifnr"], [])
    if not vms:
        return "REVIEW", ["VENDOR_NOT_FOUND"], 0.0
    if len(vms) > 1:
        codes.append("VENDOR_MASTER_DUPLICATE"); status = "REVIEW"
    vm = vms[0]
    if any(v["SPERR"].strip() for v in vms):
        return "FAIL", codes + ["VENDOR_BLOCKED"], abs(ci["amount"])
    if any(v["LOEVM"].strip() for v in vms):
        return "FAIL", codes + ["VENDOR_DELETED"], abs(ci["amount"])

    if not ci["bank_on_inv"]:
        return status, codes, protected

    rows = bank_by.get(ci["lifnr"], [])
    current = {b["BANKN"].strip() for b in rows if b["IS_CURRENT"].strip().upper() == "Y"}
    allacc = {b["BANKN"].strip() for b in rows}
    if ci["bank_on_inv"] not in allacc:
        codes.append("BANK_ACCOUNT_UNKNOWN"); status = "REVIEW"
    elif ci["bank_on_inv"] not in current:
        codes.append("BANK_MISMATCH"); status = "REVIEW"

    sig_auth = sig_domain = sig_external = sig_value = False
    for e in emh_by.get(ci["lifnr"], []):
        if e["MSG_TYPE"].strip() != "bank_change_request":
            continue
        if e["SPF"].strip() != "pass" or e["DKIM"].strip() != "pass" or e["DMARC"].strip() == "fail":
            sig_auth = True
        if domain(e["FROM_ADDR"]) and domain(vm["EMAIL"]) and domain(e["FROM_ADDR"]) != domain(vm["EMAIL"]):
            sig_domain = True
    ext_rows = [b for b in rows if b["CHANGE_SOURCE"].strip().upper() == "EMAIL"
                or b["CHANGED_BY"].strip().upper() == "EXTERNAL"]
    if ext_rows:
        sig_external = True
        if abs(ci["amount"]) >= POLICY["high_value_threshold"] and ci["bldat"]:
            for b in ext_rows:
                vf, _ = parse_date(b["VALID_FROM"])
                if vf and abs((ci["bldat"] - vf).days) <= POLICY["bank_change_freeze_days"]:
                    sig_value = True

    n = sum([sig_auth, sig_domain, sig_external, sig_value])
    if n >= 3:
        return "FAIL", codes + ["BEC_SUSPECTED"], abs(ci["amount"])
    if n >= 1:
        return "REVIEW", codes + ["BANK_CHANGE_UNVERIFIED"], abs(ci["amount"])
    return status, codes, protected


def fx_to_myr(cur, when):
    if cur == "MYR":
        return 1.0, None
    series = fx_by.get((cur, "MYR"), [])
    prior = [(d, r) for d, r in series if when is None or d <= when]
    if not prior:
        return None, None
    d, r = prior[-1]
    return r, d


def op_entity(ci):
    """Operator 5."""
    codes, status = [], "PASS"
    if ci["bukrs_on_inv"] and ci["is_po"]:
        h = ekko_by.get(ci["ebeln"])
        if h and ci["bukrs_on_inv"] != h["BUKRS"].strip():
            return "FAIL", ["ENTITY_MISMATCH"], abs(ci["amount"])

    rate, _ = fx_to_myr(ci["waers"], ci["bldat"] or POLICY["as_of_date"])
    if rate is None:
        codes.append("FX_RATE_MISSING"); status = "REVIEW"
        amount_myr = None
    else:
        amount_myr = abs(ci["amount"]) * rate

    if amount_myr is not None:
        band = [d for d in doa
                if d["KOSTL"].strip() == POLICY["default_kostl"]
                and (amt(d["MIN_AMT"]) or 0) <= amount_myr <= (amt(d["MAX_AMT"]) or 0)]
        if not band:
            codes.append("DOA_BAND_NOT_FOUND"); status = "REVIEW"

    if not ci["is_po"]:
        codes.append("NON_PO_APPROVAL"); status = "REVIEW"
        if not ci["gl_code"] or ci["gl_code"] not in gl_by:
            codes.append("GL_CODING_REQUIRED")
    return status, codes, 0.0


def run(gr_policy):
    out = []
    for r in inv:
        ci, st1, codes1 = canonical(r)
        if ci is None:
            out.append({
                "belnr": r["BELNR"].strip(), "verdict": "DATA_ERROR",
                "reason_codes": ";".join(codes1), "currency": r["WAERS"].strip(),
                "money_protected": 0.0, "spend_under_review": 0.0,
            })
            continue

        results = [("normalize", st1, codes1, 0.0),
                   ("duplicate", *op_duplicate(ci)),
                   ("bank", *op_bank(ci)),
                   ("entity", *op_entity(ci))]
        if ci["is_po"]:
            results.append(("three_way", *op_three_way(ci, gr_policy)))

        codes, fails = [], []
        for _, st, cs, prot in results:
            codes.extend(cs)
            if st == "FAIL":
                fails.append(prot)
        statuses = {st for _, st, _, _ in results}

        if "FAIL" in statuses:
            verdict = "PAYMENT_HOLD"
        elif "ERROR" in statuses:
            verdict = "DATA_ERROR"
        elif "REVIEW" in statuses:
            verdict = "HUMAN_REVIEW"
        else:
            verdict = "PAY_READY"

        # conservative: one invoice held once = one amount protected
        protected = max(fails) if (verdict == "PAYMENT_HOLD" and fails) else 0.0
        under_review = abs(ci["amount"]) if verdict == "HUMAN_REVIEW" else 0.0

        out.append({
            "belnr": ci["belnr"], "verdict": verdict,
            "reason_codes": ";".join(dict.fromkeys(codes)),
            "currency": ci["waers"],
            "money_protected": round(protected, 2),
            "spend_under_review": round(under_review, 2),
        })
    return out


def summarise(rows, label):
    v = Counter(r["verdict"] for r in rows)
    total = len(rows)
    touchless = v["PAY_READY"] / total
    prot = defaultdict(float)
    under = defaultdict(float)
    for r in rows:
        prot[r["currency"]] += r["money_protected"]
        under[r["currency"]] += r["spend_under_review"]
    print(f"\n--- {label} ---")
    for k in ("PAY_READY", "HUMAN_REVIEW", "PAYMENT_HOLD", "DATA_ERROR"):
        print(f"  {k:14s} {v[k]:>4}")
    print(f"  touchless      {touchless:.1%}")
    print("  money protected:   " + ", ".join(f"{c} {a:,.2f}" for c, a in sorted(prot.items()) if a))
    print("  spend under review:" + ", ".join(f" {c} {a:,.2f}" for c, a in sorted(under.items()) if a))
    codes = Counter(c for r in rows for c in r["reason_codes"].split(";") if c)
    print("  top reason codes: " + ", ".join(f"{k}={n}" for k, n in codes.most_common(12)))


if __name__ == "__main__":
    strict = run("strict_require_gr")
    fo = run("fo_aware")
    summarise(strict, "gr_policy = strict_require_gr")
    summarise(fo, "gr_policy = fo_aware")

    path = os.path.join(HERE, "EXPECTED_ORACLE_R2.csv")
    fo_by = {r["belnr"]: r for r in fo}
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["belnr", "verdict_strict", "reason_codes_strict",
                    "verdict_fo_aware", "reason_codes_fo_aware",
                    "currency", "money_protected_fo", "spend_under_review_fo"])
        for r in strict:
            g = fo_by[r["belnr"]]
            w.writerow([r["belnr"], r["verdict"], r["reason_codes"],
                        g["verdict"], g["reason_codes"], r["currency"],
                        g["money_protected"], g["spend_under_review"]])
    print(f"\nWrote {path} ({len(strict)} rows)")
