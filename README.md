# SWU Indexer

A standalone Star Wars Unlimited set index PDF builder using TCGAPI and optional SWU-DB ordering.

## Files
- `swu_price_indexer.py` — main script
- `requirements.txt` — runtime dependency hints for the project
- `.gitignore` — ignore virtual environments and caches

## Run

From this project root:

```bash
python3 ./swu_price_indexer.py --help
```

The script will detect missing dependencies and try to install them automatically. If automatic bootstrapping is not possible in your environment, install the two required libraries manually:

```bash
python3 -m pip install requests reportlab
```

Then run the script again.

## Notes
- The script may create a local dependency environment under `~/.swu_indexer/venv` if direct package installation is not allowed.
- It writes cache and config data to `~/.swu_indexer/`.
- Use `--force-refresh` to ignore cached API data and refetch from TCGAPI.
