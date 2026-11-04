"""Download the configured NISAR granules from ASF. Needs a NASA Earthdata account.

usage: python download_products.py [--products GUNW,GOFF] [--group pair-a] [--dry-run] [--qa-only]

--qa-only fetches just each granule's QA summary, QA report and browse picture (a few MB) and prints a go/no-go table,
so a pair can be judged and the login proven before a multi-GB download. It also supplies prepare_previews.py.

Credentials, first match wins, and never written anywhere by this script:
  EARTHDATA_TOKEN environment variable, or a `machine urs.earthdata.nasa.gov` entry in ~/.netrc (~/_netrc on Windows).
"""
import argparse
import json
import netrc
import os
import pathlib
import re
import sys

ROOT =pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "processing/src"))
from cascade_lens import pipeline, quality  # noqa: E402

HOST = "urs.earthdata.nasa.gov"
TOKEN_SHAPE = re.compile(r"[\w-]+\.[\w-]+\.[\w-]+")
HELP ="Check the credentials, and that the account has accepted the ASF EULA by signing in to https://search.asf.alaska.edu once."


def session():
    import asf_search as asf

    s = asf.ASFSession()
    token = os.environ.get("EARTHDATA_TOKEN")
    if token:
        if not TOKEN_SHAPE.fullmatch(token):  # Never echo the value: it may be something else private from the clipboard
            sys.exit(f"EARTHDATA_TOKEN is set, but it is not an Earthdata token ({len(token)} characters). A token is one long string of three dot-separated parts.\n"
                     "Copy it again from https://urs.earthdata.nasa.gov/user_tokens and save it again. Nothing was downloaded.")
        try:
            return s.auth_with_token(token)
        except asf.ASFAuthenticationError:
            sys.exit(f"Earthdata rejected the token: it may have expired or been revoked. Generate a new one at https://urs.earthdata.nasa.gov/user_tokens. {HELP}")
    for name in (".netrc", "_netrc"):
        p = pathlib.Path.home() / name
        if p.exists():
            auth = netrc.netrc(str(p)).authenticators(HOST)
            if auth:
                return s.auth_with_creds(auth[0], auth[2])
    sys.exit(f"No Earthdata credentials found. Set EARTHDATA_TOKEN or add `machine {HOST} login ... password ...` to ~/.netrc.\n"
             "See docs/DATA_ACQUISITION.md. Nothing was downloaded.")


def fetch_sidecars(picks: list[dict], s) -> None:
    """Writes to data/raw/nisar/qa and data/qa/precheck.md. Prints what NISAR's own QA says, for a person to judge."""
    folder = ROOT / "data/raw/nisar/qa"
    folder.mkdir(parents=True, exist_ok=True)
    rows = ["| Group | Product | Frame | Checks | Failed | Highest % NaN |", "|---|---|---|---|---|---|"]
    for g in picks:
        for suffix, url in (g.get("sidecars") or {}).items():
            target = folder / f"{g['file_id']}{suffix}"
            if not target.exists():
                r = s.get(url, stream=True)
                if r.status_code != 200 or "text/html" in r.headers.get("Content-Type", ""):
                    sys.exit(f"Could not fetch {target.name}: HTTP {r.status_code}. {HELP}")
                target.write_bytes(r.content)
        csv_path = folder / f"{g['file_id']}_QA_SUMMARY.csv"
        if csv_path.exists():
            q = quality.read_qa_summary(csv_path)
            nan = max(q["percent_nan"].values(), default=0)
            rows.append(f"| {g['group']} | {g['product']} | {g['frame']} | {q['checks']} | {'; '.join(q['failed']) or 'none'} | {nan:.1f} |")
    report = ROOT / "data/qa/precheck.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# NISAR QA pre-check\n\nFrom each granule's own QA summary. A failed check needs reading, not automatic rejection.\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
    print("\n".join(rows))
    print(f"-> {report}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", default="GUNW,GOFF", help="comma list; GCOV granules are 7-9 GB each")
    ap.add_argument("--group", help="only this pair or snapshot id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--qa-only", action="store_true", help="fetch QA and browse sidecars only")
    a = ap.parse_args()
    cfg = json.loads((ROOT / "processing/configs/pipeline.json").read_text())
    cat = json.loads((ROOT / "data/metadata/catalogue.json").read_text())
    picks = [g for g in pipeline.select_granules(cat, cfg) if g["product"] in a.products.split(",") and (not a.group or g["group"] == a.group)]
    todo = [g for g in picks if not pipeline.granule_path(ROOT / "data/raw", g).exists()]
    print(f"{len(picks)} selected, {len(todo)} to download, {sum(g['size_mb'] or 0 for g in todo) / 1e3:.1f} GB")
    for g in picks:
        print(" ", g["group"], g["product"], f"frame {g['frame']}", f"{g['size_mb']} MB", "(present)" if g not in todo else "")
    if a.dry_run:
        return
    if a.qa_only:
        return fetch_sidecars(picks, session())
    if not todo:
        return
    import asf_search as asf

    dest = ROOT / "data/raw/nisar"
    dest.mkdir(parents=True, exist_ok=True)
    s = session()
    try:
        asf.download_urls(urls=[g["url"] for g in todo], path=str(dest), session=s, processes=1)
    except Exception as e:  # ASF reports expired tokens and unaccepted EULAs here
        network = "Timeout" in type(e).__name__ or "Connection" in type(e).__name__
        sys.exit(f"Download failed: {type(e).__name__}: {e}\n{'Network problem: rerun this command, finished files are skipped.' if network else HELP}")
    # A partial file would look present on the next run, so compare against the catalogue size
    short = [g["file_id"] for g in todo if (p := pipeline.granule_path(ROOT / "data/raw", g)).exists() and g["size_mb"] and abs(p.stat().st_size / 1e6 - g["size_mb"]) > 1]
    missing = [g["file_id"] for g in todo if not pipeline.granule_path(ROOT / "data/raw", g).exists()]
    if short or missing:
        sys.exit(f"Incomplete download. Delete and retry: wrong size {short}, missing {missing}")
    print("All files present at their catalogue size.")


if __name__ == "__main__":
    main()
