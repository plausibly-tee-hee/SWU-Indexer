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

## TCGAPI Setup

The script requires a free TCGAPI account and API key to fetch card data.

### Create a TCGAPI Account
1. Visit [https://tcgapi.dev/](https://tcgapi.dev/)
2. Sign up for a free account
3. Verify your email address

### Generate an API Key
On your first run, the script will prompt for your TCGAPI email and password. It will then:
1. Log in to your account
2. Create an API key (typically shown once)
3. Save the key locally to `~/.swu_indexer/config.json`

Alternatively, you can create an API key manually via the TCGAPI dashboard and set the environment variable:

```bash
export TCGAPI_KEY="your_api_key_here"
python3 ./swu_price_indexer.py
```

The script will use the environment variable if set, avoiding the login prompt.

### Free Tier Limits
- TCGAPI free tier allows reasonable API usage for personal projects
- The script caches results for 3–7 days to minimize API calls
- Use `--force-refresh` to bypass cache and refetch all data

## Notes
- The script may create a local dependency environment under `~/.swu_indexer/venv` if direct package installation is not allowed.
- It writes cache and config data to `~/.swu_indexer/`.
- Use `--force-refresh` to ignore cached API data and refetch from TCGAPI.
