#!/usr/bin/env python3
"""
SWU Set Index PDF Builder (TCGAPI + optional SWU-DB), optimized for minimal API calls.

Primary goals:
- Fewest TCGAPI requests possible: use /games/:slug/sets + /sets/:id/cards (paged, per_page=200)
- Interactive set selection
- Auto dependency install
- Optional SWU-DB canonical ordering + set-size detection
- PDF output close to your Lawless Time index layout (tight table, repeat header) [1](https://outlook.office365.com/owa/?ItemID=AAMkADRhMTczZGJkLThhYTktNGNmMi1hOWRlLTI1MTQ1YjQ0MTJlOABGAAAAAADBQXbo9rcvSJgQANsx5AzDBwCBpyvi0UDGS79TV5MsEYB1AAAAAAEJAACBpyvi0UDGS79TV5MsEYB1AAIVG5%2bPAAA%3d&exvsurl=1&viewmodel=ReadMessageItem)
"""

import os, sys, json, time, re, math, argparse, subprocess
from pathlib import Path

APP_DIR = Path.home() / ".swu_indexer"
APP_DIR.mkdir(parents=True, exist_ok=True)
VENV_DIR = APP_DIR / "venv"
CONFIG_PATH = APP_DIR / "config.json"
CACHE_DIR = APP_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------
# Dependency bootstrap
# ---------------------------
REQUIRED_PKGS = ["requests", "reportlab"]


def install_with_pip(python_executable, packages, extra_args=None):
    cmd = [str(python_executable), "-m", "pip", "install", *(extra_args or []), *packages]
    subprocess.check_call(cmd)


def create_local_venv():
    if not VENV_DIR.exists():
        print("[+] Creating local virtual environment for SWU Price Indexer...")
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])
    python_exe = VENV_DIR / "bin" / "python"
    if not python_exe.exists():
        raise RuntimeError(f"Failed to create local venv at {VENV_DIR}")
    return python_exe


def reexec_in_venv(venv_python):
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(VENV_DIR)
    env["PATH"] = str(venv_python.parent) + os.pathsep + env.get("PATH", "")
    env["SWU_INDEXER_BOOTSTRAP_DONE"] = "1"
    print(f"[+] Re-launching inside local venv: {venv_python}")
    os.execvpe(str(venv_python), [str(venv_python), *sys.argv], env)


def ensure_deps():
    missing = []
    for pkg in REQUIRED_PKGS:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if not missing:
        return

    print(f"[+] Missing dependencies: {', '.join(missing)}")
    print("[+] Installing via pip...")
    try:
        install_with_pip(sys.executable, missing)
        print("[+] Dependencies installed.\n")
        return
    except subprocess.CalledProcessError:
        print("[!] pip install failed in this Python environment.")

    print("[+] Trying user-level install...")
    try:
        install_with_pip(sys.executable, missing, ["--user"])
        print("[+] Dependencies installed to user site-packages.\n")
        return
    except subprocess.CalledProcessError:
        print("[!] User-level install failed or is not allowed.")

    if os.environ.get("SWU_INDEXER_BOOTSTRAP_DONE") != "1":
        venv_python = create_local_venv()
        install_with_pip(venv_python, missing)
        reexec_in_venv(venv_python)

    raise RuntimeError(
        "Failed to install required dependencies. Please activate a Python venv or install requests and reportlab manually."
    )


ensure_deps()

import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

# ---------------------------
# Endpoints (TCGAPI + SWU-DB)
# ---------------------------
TCGAPI_BASE = "https://api.tcgapis.com/api/v1"
# Relevant documented endpoints:
# - POST /auth/login and POST /keys to create API key (cookie session)
# - GET /games/{slug}/sets to list sets
# - GET /sets/:id/cards to fetch cards in a set
# See: https://tcgapis.com/documentation

SWUDB_SEARCH = "https://api.swu-db.com/cards/search"  # q=set:law, order=setnumber [3](https://docs.tcgplayer.com/docs/getting-started)

GAME_SLUG = "star-wars-unlimited"

# ---------------------------
# Local config/cache
# ---------------------------
APP_DIR = Path.home() / ".swu_indexer"
APP_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = APP_DIR / "config.json"
CACHE_DIR = APP_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def load_json(path, default=None):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default

def save_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def now_ts():
    return int(time.time())

def is_fresh(ts, max_age_seconds):
    return ts and (now_ts() - ts) < max_age_seconds

# ---------------------------
# Helpers
# ---------------------------
def norm_collector_number(n):
    """
    Handles your tricky bit:
    - '12/264' -> 12
    - '265' -> 265
    """
    if n is None:
        return None, None
    s = str(n).strip()
    if not s:
        return None, s
    m = re.match(r"^\s*(\d+)\s*/\s*\d+\s*$", s)
    if m:
        return int(m.group(1)), s
    m2 = re.match(r"^\s*(\d+)\s*$", s)
    if m2:
        return int(m2.group(1)), s
    return None, s

def normalize_name(name):
    if not name:
        return ""
    s = name.lower().strip()
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"\s+", " ", s)
    return s

def strip_subtitle(name):
    # "Han Solo - Something" -> "Han Solo"
    if not name:
        return ""
    parts = name.split(" - ", 1)
    return parts[0].strip()

def money(x):
    if x is None or x == "":
        return ""
    try:
        return f"${float(x):.2f}"
    except Exception:
        return ""

def pick_price(card_obj):
    # TCGAPI responses commonly include pricing fields in search results (market_price, etc.) [7](https://tcgapi.dev/api/prices/)[8](https://tcgapi.dev/)
    for k in ("market_price", "price", "low_price", "median_price"):
        v = card_obj.get(k)
        if v is not None:
            return v
    return None

# ---------------------------
# TCGAPI Auth + Key (optional)
# ---------------------------
def get_api_key(session: requests.Session):
    """
    Try to retrieve TCGAPI key from environment or config.
    Returns None if not found (API calls will work without auth if supported).
    """
    # First, prefer env var
    env_key = os.environ.get("TCGAPI_KEY")
    if env_key:
        print("[+] Using TCGAPI_KEY from environment variable")
        return env_key

    cfg = load_json(CONFIG_PATH, default={}) or {}
    if cfg.get("tcgapi_key"):
        print("[+] Using TCGAPI_KEY from saved config")
        return cfg["tcgapi_key"]

    print("[+] No TCGAPI key found. Attempting unauthenticated requests.")
    print("[+] Note: If you hit rate limits, set TCGAPI_KEY environment variable.\n")
    return None

# ---------------------------
# TCGAPI Data fetch (min calls)
# ---------------------------
def tcgapi_get(session, path, api_key=None, params=None):
    url = f"{TCGAPI_BASE}{path}"
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    r = session.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def list_sets(session, api_key, use_cache=True):
    """
    GET /games/{slug}/sets (paged). [5](https://tcgapi.dev/api-explorer/)
    Cache for 7 days to avoid calls.
    """
    cache_path = CACHE_DIR / f"{GAME_SLUG}_sets.json"
    cached = load_json(cache_path, default=None)
    if use_cache and cached and is_fresh(cached.get("_ts"), 7 * 24 * 3600):
        return cached["data"]

    all_sets = []
    page = 1
    per_page = 200
    while True:
        js = tcgapi_get(session, f"/games/{GAME_SLUG}/sets", api_key=api_key, params={"page": page, "per_page": per_page})
        data = js.get("data") or []
        meta = js.get("meta") or {}
        all_sets.extend(data)
        if not meta.get("has_more"):
            break
        page += 1

    save_json(cache_path, {"_ts": now_ts(), "data": all_sets})
    return all_sets

def fetch_set_cards(session, api_key, set_id, force_refresh=False):
    """
    GET /sets/:id/cards (paged). [2](https://tcgapi.dev/api/sets/)[6](https://github.com/gordy-ftw/tcgapi-js/blob/main/README.md)
    Cache for 3 days by default (TCGAPI says many games refresh every ~3 days). [8](https://tcgapi.dev/)
    """
    cache_path = CACHE_DIR / f"set_{set_id}_cards.json"
    cached = load_json(cache_path, default=None)
    if not force_refresh and cached and is_fresh(cached.get("_ts"), 3 * 24 * 3600):
        return cached["data"]

    cards = []
    page = 1
    per_page = 200  # SDK docs mention a 200/page cap on iterate flows [6](https://github.com/gordy-ftw/tcgapi-js/blob/main/README.md)
    while True:
        js = tcgapi_get(session, f"/sets/{set_id}/cards", api_key=api_key, params={"page": page, "per_page": per_page})
        data = js.get("data") or []
        meta = js.get("meta") or {}
        cards.extend(data)
        if not meta.get("has_more"):
            break
        page += 1

    save_json(cache_path, {"_ts": now_ts(), "data": cards})
    return cards

# ---------------------------
# SWU-DB canonical base list (optional but recommended)
# ---------------------------
def swudb_cards_for_set(set_code):
    """
    SWU-DB: q=set:law&order=setnumber [3](https://docs.tcgplayer.com/docs/getting-started)
    """
    params = {"q": f"set:{set_code}", "order": "setnumber"}
    r = requests.get(SWUDB_SEARCH, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

# ---------------------------
# Variant bucketing for PDF columns
# ---------------------------
def bucket_variants(base_cards, tcg_cards):
    """
    Build rows:
    Card Name | R | R$ | H | H$ | HF | HF$ | ShF | P | P$ | PF | PF$

    Assumptions/heuristics:
    - Base set size N derived from SWU-DB max 'R' where 'setnumber' exists.
    - "R$" is often R + N (as in your Lawless Time index) [1](https://outlook.office365.com/owa/?ItemID=AAMkADRhMTczZGJkLThhYTktNGNmMi1hOWRlLTI1MTQ1YjQ0MTJlOABGAAAAAADBQXbo9rcvSJgQANsx5AzDBwCBpyvi0UDGS79TV5MsEYB1AAAAAAEJAACBpyvi0UDGS79TV5MsEYB1AAIVG5%2bPAAA%3d&exvsurl=1&viewmodel=ReadMessageItem)
    - TCGAPI objects may include fields like number/printing/variant; we use what’s present. [7](https://tcgapi.dev/api/prices/)[8](https://tcgapi.dev/)
    """
    # compute set size N from base card list
    r_vals = []
    for c in base_cards:
        r_int, _ = norm_collector_number(c.get("setnumber"))
        if r_int is not None:
            r_vals.append(r_int)
    N = max(r_vals) if r_vals else None

    # index tcg cards by normalized name (with subtitle and without)
    name_map = {}
    for c in tcg_cards:
        nm = normalize_name(c.get("name") or c.get("clean_name") or "")
        if nm:
            name_map.setdefault(nm, []).append(c)
        nm2 = normalize_name(strip_subtitle(c.get("name") or ""))
        if nm2:
            name_map.setdefault(nm2, []).append(c)

    rows = []
    for b in base_cards:
        card_name = b.get("name") or ""
        r_int, r_raw = norm_collector_number(b.get("setnumber"))

        key1 = normalize_name(card_name)
        key2 = normalize_name(strip_subtitle(card_name))
        candidates = name_map.get(key1, []) + name_map.get(key2, [])

        def get_printing(c):
            # printing names vary by game; prices doc explains printing filtering concept [7](https://tcgapi.dev/api/prices/)
            return str(c.get("printing") or c.get("print_type") or c.get("variant") or "").lower()

        def get_num(c):
            return norm_collector_number(c.get("number"))

        # initialize buckets
        buckets = {
            "R": None, "R$": None,
            "H": None, "HF": None, "ShF": None,
            "P": None, "PF": None
        }

        # choose candidates by heuristics
        for c in candidates:
            n_int, n_raw = get_num(c)
            pr = get_printing(c)
            price = pick_price(c)
            cid = c.get("id")

            # detect promo/showcase via keywords
            is_showcase = "showcase" in pr or "showcase" in (c.get("name","").lower())
            is_promo = "promo" in pr or "promo" in (c.get("set_name","").lower() if c.get("set_name") else "")

            # Determine regular vs hyperspace by number range if N is known
            is_regular_num = (N is not None and n_int is not None and 1 <= n_int <= N and "/" in (n_raw or ""))
            is_hyperspace_num = (N is not None and n_int is not None and (N+1) <= n_int <= (2*N))
            # Foil inference
            is_foil = ("foil" in pr) or ("holo" in pr)

            def better(existing, new):
                # prefer entries with a price; otherwise first seen
                if existing is None:
                    return True
                ex_price = pick_price(existing) is not None
                new_price = pick_price(new) is not None
                return (new_price and not ex_price)

            if is_showcase:
                if better(buckets["ShF"], c):
                    buckets["ShF"] = c
                continue

            if is_promo:
                # promo foil vs promo normal
                if is_foil:
                    if better(buckets["PF"], c):
                        buckets["PF"] = c
                else:
                    if better(buckets["P"], c):
                        buckets["P"] = c
                continue

            # Regular / Hyperspace assignments
            if is_regular_num:
                if is_foil:
                    if better(buckets["H"], c):
                        buckets["H"] = c
                else:
                    if better(buckets["R"], c):
                        buckets["R"] = c

            if is_hyperspace_num:
                if is_foil:
                    if better(buckets["HF"], c):
                        buckets["HF"] = c
                else:
                    if better(buckets["R$"], c):
                        buckets["R$"] = c

        # Build output columns
        # Note: In your PDF, the "R" column is the base number (1..N),
        # and "R$" often equals R+N. [1](https://outlook.office365.com/owa/?ItemID=AAMkADRhMTczZGJkLThhYTktNGNmMi1hOWRlLTI1MTQ1YjQ0MTJlOABGAAAAAADBQXbo9rcvSJgQANsx5AzDBwCBpyvi0UDGS79TV5MsEYB1AAAAAAEJAACBpyvi0UDGS79TV5MsEYB1AAIVG5%2bPAAA%3d&exvsurl=1&viewmodel=ReadMessageItem)
        r_dollar = (r_int + N) if (r_int is not None and N is not None) else None

        def id_str(c): return str(c.get("id")) if c and c.get("id") is not None else ""
        def price_str(c): return money(pick_price(c))

        row = [
            card_name,
            str(r_int) if r_int is not None else "",
            str(r_dollar) if r_dollar is not None else "",
            id_str(buckets["H"]),  price_str(buckets["H"]),
            id_str(buckets["HF"]), price_str(buckets["HF"]),
            id_str(buckets["ShF"]),
            id_str(buckets["P"]),  price_str(buckets["P"]),
            id_str(buckets["PF"]), price_str(buckets["PF"]),
        ]
        rows.append(row)

    return rows

# ---------------------------
# PDF writer (tight like your index)
# ---------------------------
def write_pdf(out_path, title, rows):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        out_path,
        pagesize=landscape(letter),
        leftMargin=0.35*inch,
        rightMargin=0.35*inch,
        topMargin=0.35*inch,
        bottomMargin=0.35*inch,
        title=title
    )

    header = ["Card Name","R","R$","H","H$","HF","HF$","ShF","P","P$","PF","PF$"]
    data = [header] + rows

    col_widths = [
        3.30*inch,  # Card Name
        0.35*inch,  # R
        0.45*inch,  # R$
        0.55*inch,  # H
        0.55*inch,  # H$
        0.55*inch,  # HF
        0.55*inch,  # HF$
        0.55*inch,  # ShF
        0.45*inch,  # P
        0.55*inch,  # P$
        0.45*inch,  # PF
        0.55*inch,  # PF$
    ]

    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE", (0,0), (-1,-1), 7),
        ("FONTSIZE", (0,0), (-1,0), 7.5),
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("LINEBELOW", (0,0), (-1,0), 0.6, colors.black),
        ("GRID", (0,0), (-1,-1), 0.25, colors.lightgrey),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (1,1), (-1,-1), "CENTER"),
        ("ALIGN", (0,0), (0,-1), "LEFT"),
        ("LEFTPADDING", (0,0), (-1,-1), 2),
        ("RIGHTPADDING", (0,0), (-1,-1), 2),
        ("TOPPADDING", (0,0), (-1,-1), 1),
        ("BOTTOMPADDING", (0,0), (-1,-1), 1),
    ]))

    story = []
    story.append(Paragraph(f"<b>{title}</b>", styles["Title"]))
    story.append(Spacer(1, 0.12*inch))
    story.append(t)
    doc.build(story)

# ---------------------------
# Interactive selection + run
# ---------------------------
def choose_set_interactive(sets):
    # display a simple numbered menu
    print("\nAvailable Star Wars Unlimited sets:")
    for i, s in enumerate(sets, start=1):
        name = s.get("name", "")
        abbr = s.get("abbreviation", "") or s.get("abbr", "")
        cc = s.get("card_count", "")
        print(f"  {i:2d}. {name} ({abbr}) cards:{cc}")
    while True:
        sel = input("\nChoose a set number: ").strip()
        if sel.isdigit():
            idx = int(sel)
            if 1 <= idx <= len(sets):
                return sets[idx-1]
        print("Invalid selection. Try again.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-refresh", action="store_true", help="Ignore caches and refetch from API")
    args = parser.parse_args()

    session = requests.Session()

    api_key = get_api_key(session)

    sets = list_sets(session, api_key, use_cache=not args.force_refresh)
    chosen = choose_set_interactive(sets)

    set_id = chosen.get("id")
    set_name = chosen.get("name", "SWU Set")
    out_name = re.sub(r"[^A-Za-z0-9]+", "", set_name) + "Index.pdf"
    out_path = str(Path.cwd() / out_name)

    print(f"\n[+] Selected: {set_name} (set_id={set_id})")
    print("[+] Fetching TCGAPI set cards (cached if available)...")
    tcg_cards = fetch_set_cards(session, api_key, set_id, force_refresh=args.force_refresh)

    # Optional SWU-DB ordering
    guessed_code = (chosen.get("abbreviation") or "").lower()
    swudb_code = input(f"\nOptional: SWU-DB set code for canonical ordering (ENTER to accept '{guessed_code}' or leave blank to skip): ").strip().lower()
    if swudb_code == "":
        swudb_code = guessed_code

    base_cards = None
    if swudb_code:
        try:
            print(f"[+] Fetching base list from SWU-DB set:{swudb_code} ...")
            base_cards = swudb_cards_for_set(swudb_code)
        except Exception as e:
            print(f"[!] SWU-DB fetch failed ({e}). Falling back to TCGAPI ordering.")
            base_cards = None

    if not base_cards:
        # fallback: build a "base" list from TCGAPI entries (best-effort)
        # Keep only entries that look like base numbering "x/y"
        base = []
        for c in tcg_cards:
            n_int, n_raw = norm_collector_number(c.get("number"))
            if n_raw and "/" in n_raw:
                base.append({"name": c.get("name"), "setnumber": n_raw})
        # sort by extracted integer
        base.sort(key=lambda x: (norm_collector_number(x.get("setnumber"))[0] or 999999))
        base_cards = base

    print("[+] Bucketing variants + building rows...")
    rows = bucket_variants(base_cards, tcg_cards)

    title = f"{set_name} Set Index"
    print(f"[+] Writing PDF: {out_path}")
    write_pdf(out_path, title, rows)
    print("\n✅ Done.")

if __name__ == "__main__":
    main()