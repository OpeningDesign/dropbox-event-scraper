# Dropbox Events Scraper

A tool to scrape and export your Dropbox activity history to CSV format for analysis and time tracking.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) - Install Docker Desktop for your operating system

## Quick Start

### Easiest: auto-capture credentials

Dropbox sessions expire every few hours, and re-doing the DevTools capture by
hand each time is tedious. `npm run refresh` automates it: it drives a local
Chrome, captures a live `/events/ajax` request, and writes `options.json` for
you (backing up the previous one to `options.json.bak`).

```bash
npm install          # once, to pull in puppeteer-core
npm run refresh
```

The first run seeds a private automation profile from your real Chrome login, so
**close all Chrome windows before the first run** (it copies your logged-in
profile, which Chrome keeps locked while open). After that, Chrome can stay open
on subsequent refreshes. It prints `Verify: POST /events/ajax -> 200 (OK)` when
the captured credentials work.

- Multiple Chrome profiles? It copies from `Default`; override with
  `CHROME_PROFILE="Profile 1"`.
- Session gone stale? Close Chrome and run `RESEED=1 npm run refresh`.
- The automation profile lives in your home dir (`~/.dropbox-event-scraper`),
  deliberately outside this folder so cookies never sync to Dropbox.

If you'd rather capture credentials by hand, follow the manual steps below.

### 1. Capture Authentication Credentials (manual)

1. Navigate to [https://www.dropbox.com/events](https://www.dropbox.com/events) in Chrome
2. Open Chrome DevTools (F12 or Right-click → Inspect)
3. Go to the **Network** tab
4. Filter by `/events/ajax` in the filter box
5. Reload the page if needed to see network requests
6. Find the first `ajax` request in the list
7. Right-click on it → **Copy** → **Copy as Node.js fetch**

The copied fetch should look similar to:

```javascript
fetch("https://www.dropbox.com/events/ajax", {
  "headers": {
    "accept": "text/plain, */*; q=0.01",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "cookie": "locale=en; gvc=...; t=...; __Host-js_csrf=...",
    // ... more headers
  },
  "body": "is_xhr=true&t=...&page_size=25&timestamp=1610559894",
  "method": "POST"
});
```

### 2. Configure options.json

Extract the options object from the fetch command and save it to `options.json`:

```json
{
  "headers": {
    "accept": "text/plain, */*; q=0.01",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-requested-with": "XMLHttpRequest",
    "cookie": "YOUR_COOKIE_STRING_HERE",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
  },
  "referrer": "https://www.dropbox.com/events",
  "referrerPolicy": "origin-when-cross-origin",
  "body": "YOUR_BODY_STRING_HERE",
  "method": "POST",
  "mode": "cors"
}
```

**Important additions:**

Add the `user-agent` header manually (choose based on your OS):

- **Windows**: 
  ```json
  "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
  ```

- **macOS**: 
  ```json
  "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
  ```

- **Linux**: 
  ```json
  "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
  ```

**⚠️ Security Warning**: Never commit `options.json` to version control - it contains your authentication cookies!

### 3. Set Date Range

Open `index.js` and modify the date range:

```javascript
const START_DATE = 'January 16, 2021 00:00:00 GMT+00:00'
const END_DATE = 'January 17, 2021 00:00:00 GMT+00:00'
```

**Date Format**: Use the format `'Month DD, YYYY HH:MM:SS GMT+00:00'`

**Examples**:
```javascript
// Last 30 days
const START_DATE = 'November 09, 2025 00:00:00 GMT+00:00'
const END_DATE = 'December 09, 2025 23:59:59 GMT+00:00'

// Specific month
const START_DATE = 'September 01, 2025 00:00:00 GMT+00:00'
const END_DATE = 'September 30, 2025 23:59:59 GMT+00:00'
```

## Running the Scraper

### Option A: Using Docker (Recommended)

1. **Open command line in the project directory**

   - **Windows**: Navigate to the folder, hold Shift + Right-click → "Open PowerShell window here"
   - **macOS/Linux**: Open Terminal and `cd` to the project directory

2. **Build the Docker image**
   ```bash
   docker build -t scraper .
   ```

3. **Run the scraper**

   `options.json` and the output CSV are mounted at runtime, so you do **not**
   need to rebuild the image when your cookies expire.

   - **Windows (PowerShell)**
     ```powershell
     mkdir out -Force
     docker run --rm `
       -v "${PWD}/options.json:/scraper/options.json:ro" `
       -v "${PWD}/out:/scraper/out" scraper
     ```

   - **macOS/Linux**
     ```bash
     mkdir -p out
     docker run --rm \
       -v "$PWD/options.json:/scraper/options.json:ro" \
       -v "$PWD/out:/scraper/out" scraper
     ```

   - **Windows (Git Bash / MINGW64)** — prefix with `MSYS_NO_PATHCONV=1`,
     otherwise Git Bash rewrites the container-side `/scraper/...` path and the
     mount lands in the wrong place (you'll see "Could not load options.json"):
     ```bash
     mkdir -p out
     MSYS_NO_PATHCONV=1 docker run --rm \
       -v "$PWD/options.json:/scraper/options.json:ro" \
       -v "$PWD/out:/scraper/out" scraper
     ```

   The CSV appears at `./out/output.csv` as it is written — no `docker cp` step,
   and partial results survive a run that dies partway through.

4. **Override the date range without editing `index.js`** (optional)
   ```bash
   docker run --rm -e START_DATE="May 5, 2026 00:00:00 GMT+00:00" \
     -e END_DATE="July 20, 2026 00:00:00 GMT+00:00" \
     -v "$PWD/options.json:/scraper/options.json:ro" \
     -v "$PWD/out:/scraper/out" scraper
   ```

Rebuild the image only when you change `index.js` or dependencies.

### Option B: Using Node.js Directly

If you have Node.js installed locally:

1. **Install dependencies**
   ```bash
   npm install
   ```

2. **Run the scraper**
   ```bash
   node index.js
   ```

3. **Find output**
   
   The CSV file will be created at `./output.csv`

## Output Format

The scraper generates a CSV file with the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| `name` | User name | Ryan Schultz |
| `timestamp` | Unix timestamp (seconds) | 1753793081 |
| `ago` | Human-readable time | 7/29/2025 7:44 AM |
| `event_blurb` | HTML description of event | You edited &lt;a&gt;...&lt;/a&gt; |
| `blurb` | Plain text description | You edited House.ifc and 8 more files |
| `dataLink` | Full Dropbox URL to the file | https://www.dropbox.com/pri/get/... |

**Sample Output**:
```csv
name,timestamp,ago,event_blurb,blurb,dataLink
Ryan Schultz,1753793081,7/29/2025 7:44 AM,You edited <a>House.ifc</a>,You edited House.ifc,https://www.dropbox.com/pri/get/Gitea_OD/Bonsai_Tutorials/House.ifc
```

## Troubleshooting

### Authentication Error (403)

**Problem**: `Options.json seems outdated, authentication error`

**Solution**: 
1. Your cookies have expired
2. Recapture the fetch request from Chrome DevTools
3. Update `options.json` with fresh authentication data

Since `options.json` is mounted at runtime, just re-run — no rebuild needed.

To confirm the session is dead rather than the config being malformed:

```bash
node -e "const o=require('./options.json'); fetch('https://www.dropbox.com/events',{headers:{cookie:o.headers.cookie},redirect:'manual'}).then(r=>console.log(r.status, r.headers.get('location')))"
```

A `302` to `/login?cont=%2Fevents` means the cookies have expired.

Long date ranges make this more likely: the scraper issues one request per
100-event batch **plus** one per event that links to a file, so a multi-month
range can run for hours and outlive the session. If it dies partway, keep the
partial `out/output.csv` and resume by setting `END_DATE` to the oldest
timestamp you captured.

### No Events Returned

**Problem**: CSV file is empty or very small

**Possible causes**:
- Date range is outside your activity period
- The `timestamp` in the body parameter needs to be updated
- Check that your START_DATE is before END_DATE

### Same Date Repeats Forever, No Rows Written

**Problem**: the log prints the same timestamp over and over, never a
`Batch size:` line, and `output.csv` is never created. Looks like a slow scrape;
it is actually a request failing on every attempt.

**Cause**: a request parameter Dropbox rejects — most often `PAGE_SIZE` above
100. The response is an HTML error page, not JSON.

**Check it directly**:

```bash
node -e "const o=require('./options.json'); o.body=o.body.replace(/page_size=[0-9]*/,'page_size=100'); fetch('https://www.dropbox.com/events/ajax',o).then(r=>console.log(r.status))"
```

`200` is healthy; `400` means a bad parameter, `403` means expired cookies.

The scraper now fails loudly on this instead of looping — if you see the old
silent behaviour, you are running a stale image. Rebuild with `docker build -t
scraper .`

### Rate Limiting

The scraper includes a 5-second delay between requests to avoid rate limiting. For large date ranges, the script may take several minutes to complete.

## Configuration Options

### Adjusting Batch Size

In `index.js`, you can modify:

```javascript
const PAGE_SIZE = 100  // Number of events per request (max: 100)
```

**100 is a hard limit.** Dropbox rejects `page_size=101` and above with an HTTP
400 — verified by bisection. Earlier versions of this README documented a max of
250; that no longer works and produces a 400 on *every* request.

### Adjusting Request Delay

In `index.js`, find the sleep duration:

```javascript
await sleep(5000)  // 5000ms = 5 seconds
```

Increase this value if you encounter rate limiting issues.

## File Structure

```
dropbox-event-scraper/
├── index.js           # Main scraper script
├── decoder.js         # Decodes Dropbox response data
├── options.json       # Authentication credentials (DO NOT COMMIT)
├── out/output.csv     # Generated output file (Docker mount target)
├── Dockerfile         # Docker configuration
├── .dockerignore      # Keeps credentials out of the built image
├── package.json       # Node.js dependencies
└── README.md          # This file
```

## Security Best Practices

1. **Never commit `options.json`** - Add it to `.gitignore`
2. **Regenerate cookies regularly** - They contain session tokens
3. **Use a dedicated Dropbox account** for scraping if possible
4. **Review the output** before sharing - it may contain sensitive file paths

## Known Limitations

- Scraper only works with personal Dropbox accounts (not Business accounts with SSO)
- Maximum of 100 events per request (Dropbox returns HTTP 400 above this)
- Some events may not include `dataLink` if files were deleted
- Timestamps are in UTC (convert to local time in post-processing)

## Next Steps: Time Analysis

After scraping your data, use the Project Hours Analyzer to calculate time spent:

```bash
python project_hours_analyzer.py
```

See the [Project Hours Analyzer README](./project_hours_analyzer/readme.md) for details.

## Contributing

Issues and pull requests are welcome! Please ensure:
- No sensitive data in commits
- Code follows existing style
- Test with your own Dropbox account first

## License

Apache-2.0 license - See LICENSE file for details

