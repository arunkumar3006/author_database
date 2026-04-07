# Skribe API Journalist Enrichment System

A production-grade journalist data enrichment system that directly calls Skribe's internal REST API.

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Setup credentials:
   - Copy `.env.example` to `.env`
   - Fill in `SKRIBE_JWT_TOKEN`, `SKRIBE_COOKIE`, and `SKRIBE_USER_ID` from Chrome DevTools.

3. Prepare input:
   - Place your journalist list (Name and Publication/Outlet) in `input/journalists.xlsx`.

4. Run the tool:
   - **CLI Mode**: `python main.py`
   - **Modern Dashboard**: `streamlit run app.py`

## How to Get Your Credentials

To fetch the required API tokens:
1. Log into [goskribe.com](https://www.goskribe.com) in Chrome.
2. Open DevTools (F12) -> Network tab -> Filter by "Fetch/XHR".
3. Search for any journalist in the Skribe UI.
4. Click on the `GetJournalists` request.
5. In the **Headers** tab:
   - Copy the `Authorization` value (after "Bearer ").
   - Copy the `Cookie` header value.
6. In the **Payload** tab (for a `PostTracking` call, if available):
   - Copy the `userId` value.
7. Paste these into your `.env` file.

## Usage Examples

- **Resume an interrupted run:**
  ```bash
  python main.py --resume
  ```

- **Process a specific number of journalists:**
  ```bash
  python main.py --limit 30
  ```

- **Check token expiry:**
  ```bash
  python main.py --check-token
  ```

- **Dry run (validate input and token):**
  ```bash
  python main.py --dry-run
  ```

- **Custom input/output paths:**
  ```bash
  python main.py --input lists/target.xlsx --output output/results.xlsx
  ```

## Account Safety & Limits

This script is designed to protect your Skribe account:
- Enforces safe rate limits (4-8 seconds between requests).
- Targets a maximum of 400 requests per day (staying well within the 500/window limit).
- Automatically pauses if rate limits are approached.
- Mimics browser tracking calls (`PostTracking`).
- Gracefully handles token expiry and potential account flagging.

## Output Format

The enriched Excel file contains:
- `SUCCESS`: Match score >= 80
- `PARTIAL`: Match score >= 60
- `NOT_FOUND`: Match score < 60
- `ERROR`: Any error during enrichment

Each row provides: Journalist ID, Email, Phone, Twitter, LinkedIn, Beat, Location, Bio, Skribe Profile URL, Match Score, and Status.
A "Run Summary" sheet is included with session stats and token expiry info.
