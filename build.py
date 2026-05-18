#!/usr/bin/env python3
"""CLI to generate static HTML pages (in French) for honey batch traceability."""

import argparse
import html
import json
import sys

from datetime import datetime
from pathlib import Path
from string import Template

from markdown2 import markdown


DEFAULT_LOCATION = "Plaine de la Limagne, Auvergne, France"
DEFAULT_BEEKEEPER = "William Durand"

LEDGER_NAME = "batches.jsonl"

THEMES = {
    "spring": {
        "label": "Printemps",
        "title": "Miel de printemps",
        "bg": "#eaf6ee",
        "accent": "#2f9e6b",
        "accent_soft": "#cfeadb",
        "tag_fg": "#1f5a3d",
    },
    "summer": {
        "label": "Été",
        "title": "Miel d'été",
        "bg": "#fff1d6",
        "accent": "#c2410c",
        "accent_soft": "#ffd9a8",
        "tag_fg": "#7a2e08",
    },
}


THEME_VARS_TPL = Template(
    """  :root {
    --bg: $bg;
    --card: #ffffff;
    --accent: $accent;
    --accent-soft: $accent_soft;
    --text: #3a2e1f;
    --muted: #8a7a5e;
  }"""
)

PAGE_STYLE = """  * {
    box-sizing: border-box;
  }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
  }
  .card {
    background: var(--card);
    border-radius: 16px;
    border-top: 6px solid var(--accent);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
    max-width: 600px;
    padding: 1.75rem 1.25rem;
    width: 100%;
  }
  h1 {
    font-size: 1.35rem;
    letter-spacing: 0.5px;
    margin: 0.5rem 0 0.25rem;
    text-align: center;
  }
  .subtitle {
    text-align: center;
    color: var(--muted);
    margin-bottom: 2rem;
    font-size: 0.95rem;
  }
  dl {
    display: grid;
    gap: 1rem;
    margin: 0;
  }
  .row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    border-bottom: 1px dashed #eee;
    padding-bottom: 0.6rem;
    gap: 1rem;
    flex-wrap: wrap;
    flex-direction: column;
  }
  dt {
    color: var(--muted);
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  dd {
    margin: 0;
    font-weight: 600;
    text-align: right;
  }
  .explainer {
    margin-top: 1.5rem;
    padding: 1rem 1.1rem;
    background: var(--accent-soft);
    border-left: 3px solid var(--accent);
    border-radius: 8px;
    font-size: 0.95rem;
    line-height: 1.5;

    & :first-child {
      margin-top: 0;
    }

    & :last-child {
      margin-bottom: 0;
    }
  }
  footer {
    text-align: center;
    margin-top: 2rem;
    color: var(--muted);
    font-size: 0.8rem;
  }
  @media (min-width: 600px) {
    h1 {
      font-size: 1.6rem;
    }
    .card {
      padding: 2.5rem 2rem;
    }
    .row {
      flex-direction: row;
    }
  }
  @media print {
    body {
      background: #fff;
      padding: 0;
    }
    .card {
      box-shadow: none;
      border-radius: 0;
      border-top-width: 4px;
    }
  }"""

PAGE_TEMPLATE = Template(
    """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="Traçabilité du lot de miel n°$batch récolté par $beekeeper.">
<title>$title · Lot n°$batch · $beekeeper</title>
<style>
$theme_vars
$page_style
</style>
</head>
<body>
  <main class="card">
    <h1>$title</h1>
    <p class="subtitle">Numéro de lot : <strong>$batch</strong></p>
    <dl>
      <div class="row"><dt>Date de Durabilité Minimale (DDM)</dt><dd>$ddm</dd></div>
      <div class="row"><dt>Conditionné le</dt><dd>$bottled</dd></div>
      <div class="row"><dt>Récolté le</dt><dd>$harvested</dd></div>
      <div class="row"><dt>Lieu de récolte</dt><dd>$location</dd></div>$hives_row
    </dl>$explainer_block
    <footer>$beekeeper</footer>
  </main>
</body>
</html>
"""
)


def parse_iso_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        sys.exit(f"Error: invalid date '{s}' (expected YYYY-MM-DD)")


def parse_batch(batch):
    """The batch number is in DD-MM-YY format and also serves as the DDM."""
    try:
        return datetime.strptime(batch, "%d-%m-%y").date()
    except ValueError:
        sys.exit(f"Error: invalid batch number '{batch}' (expected DD-MM-YY)")


def fr_date(d):
    return d.strftime("%d/%m/%Y")


def theme_vars(theme):
    return THEME_VARS_TPL.substitute(
        bg=theme["bg"],
        accent=theme["accent"],
        accent_soft=theme["accent_soft"],
    )


def append_ledger(outdir, record):
    with (outdir / LEDGER_NAME).open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_ledger_records(outdir):
    """Return the latest record per batch (without filtering on existing HTML)."""
    path = outdir / LEDGER_NAME
    if not path.exists():
        return []
    latest = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        latest[rec["batch"]] = rec
    return list(latest.values())


def build_page(record):
    theme = THEMES[record["season"]]
    harvested = parse_iso_date(record["harvested"])
    bottled = parse_iso_date(record["bottled"])
    ddm = parse_batch(record["batch"])

    explainer_block = ""
    if record.get("explainer"):
        explainer_block = (
            f'\n    <div class="explainer">{markdown(record["explainer"])}</div>'
        )

    hives_row = ""
    hives = record.get("hives")
    if hives:
        ruche_word = "ruche" if hives == 1 else "ruches"
        hives_row = (
            f'\n      <div class="row"><dt>Nombre de ruches récoltées</dt>'
            f"<dd>{hives} {ruche_word}</dd></div>"
        )

    title = f"{theme['title']} {harvested.year}"

    return PAGE_TEMPLATE.substitute(
        batch=record["batch"],
        harvested=fr_date(harvested),
        bottled=fr_date(bottled),
        ddm=fr_date(ddm),
        location=html.escape(record["location"], quote=True),
        beekeeper=html.escape(record["beekeeper"], quote=True),
        title=title,
        theme_vars=theme_vars(theme),
        page_style=PAGE_STYLE,
        explainer_block=explainer_block,
        hives_row=hives_row,
    )


def do_rebuild(outdir):
    """Regenerate every batch HTML page from the ledger."""
    if not outdir.exists():
        sys.exit(f"Error: output directory '{outdir}' does not exist.")

    records = read_ledger_records(outdir)
    if not records:
        print(f"⚠ No batches found in {outdir / LEDGER_NAME}.")
    else:
        for rec in sorted(records, key=lambda x: parse_batch(x["batch"])):
            page_path = outdir / f"{rec['batch']}.html"
            page_path.write_text(build_page(rec), encoding="utf-8")
            print(f"✓ Page    {page_path}")


def main():
    p = argparse.ArgumentParser(
        description="Generate a honey batch HTML page (in French) with traceability."
    )
    p.add_argument(
        "batch",
        nargs="?",
        help="Batch number (format DD-MM-YY, e.g. 20-05-26). "
        "Omit when using --rebuild.",
    )
    p.add_argument("--harvested", help="Harvest date (YYYY-MM-DD)")
    p.add_argument("--bottled", help="Bottling date (YYYY-MM-DD)")
    p.add_argument(
        "--location",
        default=DEFAULT_LOCATION,
        help=f"Collection location (default: {DEFAULT_LOCATION})",
    )
    p.add_argument(
        "--season",
        choices=sorted(THEMES.keys()),
        help="Honey season (drives the page theme)",
    )
    p.add_argument(
        "--beekeeper",
        default=DEFAULT_BEEKEEPER,
        help=f"Beekeeper name (default: {DEFAULT_BEEKEEPER})",
    )
    p.add_argument(
        "--explainer",
        default=None,
        help="Optional short free-form text describing the product",
    )
    p.add_argument(
        "--hives",
        type=int,
        default=None,
        help="Number of hives this batch comes from "
        "(adds a row in the traceability details)",
    )
    p.add_argument("--outdir", default="lots", help="Output directory (default: lots)")
    p.add_argument(
        "--force", action="store_true", help="Overwrite existing HTML page if any"
    )
    p.add_argument(
        "--rebuild",
        action="store_true",
        help="Regenerate every batch page from the ledger, "
        "then exit. Ignores other batch-creation flags.",
    )
    args = p.parse_args()

    outdir = Path(args.outdir)

    if args.rebuild:
        # Reject flags that don't make sense alongside --rebuild.
        conflicting = [
            ("batch", args.batch),
            ("--harvested", args.harvested),
            ("--bottled", args.bottled),
            ("--season", args.season),
            ("--explainer", args.explainer),
            ("--hives", args.hives),
        ]
        bad = [name for name, val in conflicting if val]
        if bad:
            sys.exit(f"Error: --rebuild cannot be combined with: {', '.join(bad)}")
        do_rebuild(outdir)
        return

    missing = [
        name
        for name, val in (
            ("batch", args.batch),
            ("--harvested", args.harvested),
            ("--bottled", args.bottled),
            ("--season", args.season),
        )
        if not val
    ]
    if missing:
        sys.exit(f"Error: missing required argument(s): {', '.join(missing)}")

    if args.hives is not None and args.hives < 1:
        sys.exit(f"Error: --hives must be a positive integer (got {args.hives}).")

    ddm = parse_batch(args.batch)
    harvested = parse_iso_date(args.harvested)
    bottled = parse_iso_date(args.bottled)
    if bottled < harvested:
        sys.exit(
            f"Error: bottling date ({args.bottled}) is before harvest date ({args.harvested})."
        )
    if ddm <= bottled:
        sys.exit(
            f"Error: batch number ({args.batch}) must be after bottling date ({args.bottled})."
        )

    outdir.mkdir(parents=True, exist_ok=True)

    page_path = outdir / f"{args.batch}.html"
    if page_path.exists() and not args.force:
        sys.exit(f"Error: {page_path} already exists. Use --force to overwrite.")

    record = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "batch": args.batch,
        "harvested": args.harvested,
        "bottled": args.bottled,
        "location": args.location,
        "season": args.season,
        "beekeeper": args.beekeeper,
        "explainer": args.explainer,
        "hives": args.hives,
    }

    page_path.write_text(build_page(record), encoding="utf-8")
    print(f"✓ Page    {page_path}")

    append_ledger(outdir, record)
    print(f"✓ Ledger  {outdir / LEDGER_NAME}")


if __name__ == "__main__":
    main()
