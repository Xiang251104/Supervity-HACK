"""Populate the Command Center with real Orchestrator runs.

A judge should open the dashboard and see the AI Employee's actual working
history, not two rows from a smoke test. This drives the same public endpoint
the UI uses, so every figure on screen comes from a genuine agent run --
nothing here writes a decision directly.

Runs are slow (roughly one to three minutes each, most of it waiting on Auto),
so a few go at once. The backend is a single uvicorn worker, but `start_run`
spends its time awaiting the event stream, which leaves the loop free to serve
its neighbours.

    # a contiguous slice of the book -- the honest, unbiased sample
    python scripts/seed_demo_runs.py --range 5110000000:30

    # specific invoices, e.g. the demo narrative
    python scripts/seed_demo_runs.py 5110000002 5110000150 5110000164

    # from a file, one reference per line
    python scripts/seed_demo_runs.py --file demo_invoices.txt

Safe to re-run: a run id already present comes back 409 and is reported as
skipped. Pass --prefix to start a fresh set.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

DEFAULT_BASE_URL = "http://localhost:8001"
ALLOWED_SCHEMES = ("http", "https")
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("invoices", nargs="*", help="Invoice references to process.")
    parser.add_argument("--range", dest="ref_range", metavar="START:COUNT",
                        help="Sequential references, e.g. 5110000000:30.")
    parser.add_argument("--file", type=Path, help="File with one reference per line.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--allow-host", action="append", default=[], metavar="HOST",
                        help="Permit a non-local --base-url host, e.g. a Railway domain.")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--prefix", default=None,
                        help="Run id prefix. Defaults to DEMO-<today>.")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would run, then stop.")
    return parser.parse_args()


def validated_base_url(raw: str, extra_hosts: Sequence[str] = ()) -> str:
    """Rebuild the target from parts we have checked.

    The seeder takes its target off the command line, so the string is only
    as trustworthy as whoever typed it -- a stray value would have us posting
    invoice runs at somebody else's host. Callers use what this returns and
    never the raw argument. Local hosts are fine by default; anything else
    has to be named with --allow-host, so reaching outside is always a choice.
    """
    parts = urlsplit(raw)

    if parts.scheme not in ALLOWED_SCHEMES:
        raise SystemExit(f"--base-url needs an http:// or https:// prefix, got {raw!r}")

    try:
        host, port = parts.hostname, parts.port
    except ValueError as exc:
        raise SystemExit(f"--base-url has a bad port: {exc}") from exc

    if not host:
        raise SystemExit("--base-url needs a host, e.g. http://localhost:8001")

    if parts.username or parts.password:
        raise SystemExit("--base-url must not carry credentials")

    permitted = {h.lower() for h in LOCAL_HOSTS} | {h.lower() for h in extra_hosts}
    if host.lower() not in permitted:
        raise SystemExit(f"{host} is not an allowed target. Add --allow-host {host} if you meant it.")

    literal = f"[{host}]" if ":" in host else host  # IPv6 keeps its brackets
    netloc = f"{literal}:{port}" if port else literal
    return urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", ""))


def resolve_invoices(args: argparse.Namespace) -> list[str]:
    refs: list[str] = list(args.invoices)

    if args.ref_range:
        start_text, _, count_text = args.ref_range.partition(":")
        if not count_text:
            raise SystemExit("--range needs START:COUNT, e.g. 5110000000:30")
        start, count = int(start_text), int(count_text)
        width = len(start_text)
        refs.extend(str(start + offset).zfill(width) for offset in range(count))

    if args.file:
        refs.extend(
            line.strip() for line in args.file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        )

    # De-duplicate, keeping the order the user asked for.
    return list(dict.fromkeys(refs))


class Tally:
    def __init__(self) -> None:
        self.verdicts: dict[str, int] = {}
        self.protected: dict[str, float] = {}
        self.skipped = 0
        self.failed = 0

    def record(self, verdict: str, currency: str | None, protected: float) -> None:
        self.verdicts[verdict] = self.verdicts.get(verdict, 0) + 1
        if protected and currency:
            self.protected[currency] = self.protected.get(currency, 0.0) + protected


async def run_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    base_url: str,
    invoice_ref: str,
    run_id: str,
    tally: Tally,
) -> None:
    async with semaphore:
        started = datetime.now(timezone.utc)
        try:
            response = await client.post(
                f"{base_url}/api/ap/runs",
                json={"invoice_ref": invoice_ref, "run_id": run_id,
                      "trigger_source": "demo_seed"},
            )
        except httpx.HTTPError as exc:
            tally.failed += 1
            print(f"  {invoice_ref}  NETWORK ERROR  {exc}")
            return

        elapsed = (datetime.now(timezone.utc) - started).total_seconds()

        if response.status_code == 409:
            tally.skipped += 1
            print(f"  {invoice_ref}  skipped (run id already used)")
            return

        if response.status_code >= 400:
            tally.failed += 1
            detail = response.text[:160].replace("\n", " ")
            print(f"  {invoice_ref}  HTTP {response.status_code}  {detail}")
            return

        decision = response.json().get("decision") or {}
        verdict = decision.get("verdict", "UNKNOWN")
        protected = float(decision.get("money_protected") or 0.0)
        currency = decision.get("currency")
        codes = ", ".join(decision.get("reason_codes") or []) or "-"
        money = f"{currency} {protected:,.2f}" if protected else ""

        tally.record(verdict, currency, protected)
        print(f"  {invoice_ref}  {verdict:<14} {elapsed:6.1f}s  {money:<22} {codes}")


async def main() -> int:
    args = parse_args()
    invoices = resolve_invoices(args)
    base_url = validated_base_url(args.base_url, args.allow_host)

    if not invoices:
        raise SystemExit("No invoices given. Use positional refs, --range or --file.")

    prefix = args.prefix or f"DEMO-{datetime.now(timezone.utc):%Y%m%d}"

    print(f"{len(invoices)} invoice(s) -> {base_url}")
    print(f"run id prefix: {prefix} | concurrency: {args.concurrency}\n")

    if args.dry_run:
        for ref in invoices:
            print(f"  would run {ref}  as  {prefix}-{ref}")
        return 0

    tally = Tally()
    semaphore = asyncio.Semaphore(max(1, args.concurrency))

    async with httpx.AsyncClient(timeout=args.timeout) as client:
        try:
            await client.get(f"{base_url}/api/ap/metrics")
        except httpx.HTTPError:
            print(f"Cannot reach {base_url}. Is the stack up? (make up)")
            return 1

        await asyncio.gather(*(
            run_one(client, semaphore, base_url, ref, f"{prefix}-{ref}", tally)
            for ref in invoices
        ))

    print("\n--- summary ---")
    for verdict, count in sorted(tally.verdicts.items(), key=lambda kv: -kv[1]):
        print(f"  {verdict:<14} {count}")
    decided = sum(tally.verdicts.values())
    if decided:
        touchless = 100.0 * tally.verdicts.get("PAY_READY", 0) / decided
        print(f"  touchless      {touchless:.1f}%")
    for currency, amount in sorted(tally.protected.items()):
        print(f"  protected      {currency} {amount:,.2f}")
    if tally.skipped:
        print(f"  skipped        {tally.skipped}")
    if tally.failed:
        print(f"  failed         {tally.failed}")

    return 1 if tally.failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
