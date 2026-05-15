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

The script requires a tcgapis.com Hobby+ account and API key to access Star Wars Unlimited set data.

### Create a tcgapis.com Account
1. Visit [https://tcgapis.com/](https://tcgapis.com/)
2. Sign up for a Hobby+ account (free tier is available)
3. Verify your email address
4. Generate an API key from your dashboard

### Use Your API Key

Set the API key as an environment variable before running the script:

```bash
export TCGAPI_KEY="your_api_key_here"
python3 ./swu_price_indexer.py
```

Or the script will check for a saved key in `~/.swu_indexer/config.json`.

### API Requirements
- **Free tier**: No API access (Hobby+ required)
- **Hobby+ tier**: 300 requests/minute, 10,000/month
- The script uses offset/limit pagination to minimize API calls
- Results are cached for 3–7 days to reduce requests
- Use `--force-refresh` to bypass cache

For more details, see the [tcgapis.com documentation](https://tcgapis.com/documentation)

## Notes
- The script may create a local dependency environment under `~/.swu_indexer/venv` if direct package installation is not allowed.
- It writes cache and config data to `~/.swu_indexer/`.
- Use `--force-refresh` to ignore cached API data and refetch from TCGAPI.
