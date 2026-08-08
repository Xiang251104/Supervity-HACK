"""Generate Supabase schema SQL + lowercase import CSVs for the Round 2 pack.

Design rules (locked):
  - Dirty columns stay TEXT. Operators normalize at runtime. Never pre-clean the source.
  - Only demonstrably-clean numerics become numeric.
  - Surrogate bigserial PK everywhere (vendor_master has a duplicate lifnr; po_items is composite).
  - Indexes on every join key the Operators filter by.

The organizer dataset is NOT committed to this repository — it may not be redistributed.
Point this script at your own copy of the Round 2 csv folder:

    python generate_import_csvs.py /path/to/csv

or set AP_DATASET_DIR. Outputs land in ./import/ next to this script, which is gitignored.
"""
import csv, os, re, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))


def _dataset_dir() -> str:
    """Locate the organizer's csv folder and return it as one canonical path.

    The location has to come from outside -- the pack may not be redistributed, so
    it is not in this repo and everyone keeps it somewhere different. That makes it
    the one untrusted input here, and every file this script opens is built from
    it. Resolving it once, up front, means the rest of the script joins names onto
    a path with no symlinks and no '..' left in it, and `_source_csv` can then
    prove each result still sits directly inside it.
    """
    candidates = [
        sys.argv[1] if len(sys.argv) > 1 else None,
        os.getenv("AP_DATASET_DIR"),
        os.path.join(HERE, "..", "..", "dataset", "csv"),
    ]
    for c in candidates:
        if not c:
            continue
        resolved = os.path.realpath(c)
        if os.path.isdir(resolved) and os.path.isfile(
            os.path.join(resolved, "RBKP_Invoice.csv")
        ):
            return resolved
    raise SystemExit(
        "Could not find the Round 2 dataset.\n"
        "The organizer pack is not committed to this repo (it may not be redistributed).\n"
        "Point this script at your own copy of the csv folder, e.g.:\n"
        "    python generate_import_csvs.py /path/to/csv\n"
        "or set AP_DATASET_DIR. The folder must contain RBKP_Invoice.csv."
    )


SRC = _dataset_dir()
OUT = HERE
IMP = os.path.join(OUT, "import")
os.makedirs(IMP, exist_ok=True)


def _source_csv(name: str) -> str:
    """Path to one table's csv, proven to sit directly inside the dataset folder.

    `name` comes from the TABLES map in this file rather than from input, so this
    is belt and braces -- but it costs nothing and it means no future edit can turn
    a table name into a way out of the folder the caller pointed us at.
    """
    path = os.path.realpath(os.path.join(SRC, name + ".csv"))
    if os.path.dirname(path) != SRC or not os.path.isfile(path):
        raise SystemExit(f"{name}.csv is not a file inside {SRC}")
    return path

# source file -> supabase table name
TABLES = {
    "RBKP_Invoice":       "ap_invoices",
    "LFA1_Vendor_Master": "vendor_master",
    "EKKO_PO_Header":     "po_headers",
    "EKPO_PO_Item":       "po_items",
    "MSEG_Goods_Receipt": "goods_receipts",
    "SKA1_GL_Master":     "gl_master",
    "DOA_Matrix":         "doa_matrix",
    "KONP_Conditions":    "pricing_conditions",
    "Company_Codes":      "company_codes",
    "FX_Rates":           "fx_rates",
    "Bank_Master":        "bank_master",
    "Email_Headers":      "email_headers",
    "Discount_Schedule":  "discount_schedule",
    "Approval_Log":       "approval_log",
}

# columns that become numeric — everything else stays text
NUMERIC = {
    "po_headers":        {"netwr", "wkurs"},
    "po_items":          {"menge", "netpr", "netwr", "uebto", "untto", "peinh"},
    "goods_receipts":    {"menge"},
    "doa_matrix":        {"min_amt", "max_amt"},
    "fx_rates":          {"ukurs", "ffact", "tfact"},
    "discount_schedule": {"disc_pct", "disc_days", "net_days"},
    "ap_invoices":       {"confidence", "gst_amt"},   # wrbtr stays TEXT — comma-decimals
    "pricing_conditions": {"kbetr", "kpein"},
    "approval_log":      {"wrbtr"},
}

INDEXES = {
    "ap_invoices":       ["belnr", "lifnr", "ebeln", "xblnr"],
    "vendor_master":     ["lifnr"],
    "po_headers":        ["ebeln", "lifnr", "bukrs"],
    "po_items":          ["ebeln", "ebelp", "matnr"],
    "goods_receipts":    ["ebeln", "ebelp"],
    "gl_master":         ["saknr"],
    "doa_matrix":        ["kostl"],
    "pricing_conditions": ["knumh", "kschl"],
    "company_codes":     ["bukrs"],
    "fx_rates":          ["fcurr", "tcurr", "gdatu"],
    "bank_master":       ["lifnr", "bankn", "is_current"],
    "email_headers":     ["lifnr", "belnr", "msg_type"],
    "discount_schedule": ["lifnr"],
    "approval_log":      ["belnr", "policy_ref"],
}

def is_num(v):
    v = (v or "").strip()
    if v == "":
        return True  # blank -> NULL, doesn't disqualify
    return re.fullmatch(r"-?\d+(\.\d+)?", v) is not None

sql = []
sql.append("-- AP Control Tower — Round 2 Supabase schema")
sql.append("-- Generated from the organizer pack. Dirty columns are TEXT on purpose:")
sql.append("-- the Operators normalize comma-decimals and mixed date formats at runtime.")
sql.append("-- Run this whole file in the Supabase SQL editor, then import the CSVs in ./import/.")
sql.append("")

report = []
for src, tbl in TABLES.items():
    path = _source_csv(src)
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    cols = [c.strip().lower() for c in rows[0].keys()]

    # verify the numeric allowlist really is numeric
    numeric_cols = set()
    for c in NUMERIC.get(tbl, set()):
        if c not in cols:
            report.append(f"  !! {tbl}.{c} in NUMERIC allowlist but not a column — skipped")
            continue
        bad = [r[[k for k in r if k.strip().lower() == c][0]] for r in rows]
        if all(is_num(v) for v in bad):
            numeric_cols.add(c)
        else:
            offender = next(v for v in bad if not is_num(v))
            report.append(f"  !! {tbl}.{c} NOT clean numeric (e.g. {offender!r}) — kept TEXT")

    defs = ["  id bigserial primary key"]
    for c in cols:
        if c == "mandt":
            continue  # SAP client column, no value to us
        t = "numeric" if c in numeric_cols else "text"
        defs.append(f"  {c} {t}")

    sql.append(f"drop table if exists public.{tbl} cascade;")
    sql.append(f"create table public.{tbl} (")
    sql.append(",\n".join(defs))
    sql.append(");")
    for ix in INDEXES.get(tbl, []):
        if ix in cols:
            sql.append(f"create index on public.{tbl} ({ix});")
    sql.append("")

    # write the import CSV: lowercase headers, mandt dropped, values untouched
    keymap = {c.strip().lower(): c for c in rows[0].keys()}
    outcols = [c for c in cols if c != "mandt"]
    with open(os.path.join(IMP, tbl + ".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(outcols)
        for r in rows:
            w.writerow([(r[keymap[c]] or "").strip() if c not in numeric_cols
                        else ((r[keymap[c]] or "").strip() or "") for c in outcols])
    report.append(f"  {tbl:20s} {len(rows):>4} rows, {len(outcols)} cols"
                  f"{' , numeric: ' + ','.join(sorted(numeric_cols)) if numeric_cols else ''}")

# uniqueness check on ap_invoices.belnr
with open(_source_csv("RBKP_Invoice"), newline="", encoding="utf-8-sig") as f:
    belnrs = [r["BELNR"].strip() for r in csv.DictReader(f)]
dupe = [k for k, v in Counter(belnrs).items() if v > 1]
if dupe:
    report.append(f"  !! ap_invoices.belnr NOT unique ({len(dupe)} repeats) — no unique constraint added")
else:
    sql.append("-- belnr verified unique across the pack")
    sql.append("create unique index on public.ap_invoices (belnr);")
    sql.append("")
    report.append("  ap_invoices.belnr verified unique -> unique index added")

sql.append("-- Row counts to verify after import:")
for src, tbl in TABLES.items():
    with open(_source_csv(src), newline="", encoding="utf-8-sig") as f:
        n = sum(1 for _ in csv.DictReader(f))
    sql.append(f"--   {tbl:20s} {n}")
sql.append("")
sql.append("select 'ap_invoices' t, count(*) from public.ap_invoices")
for tbl in list(TABLES.values())[1:]:
    sql.append(f"union all select '{tbl}', count(*) from public.{tbl}")
sql.append("order by 1;")

with open(os.path.join(OUT, "schema_r2.sql"), "w", encoding="utf-8") as f:
    f.write("\n".join(sql) + "\n")

print("Wrote:", os.path.join(OUT, "schema_r2.sql"))
print("Import CSVs:", IMP)
print()
print("\n".join(report))
