# Dropbox Events Scraper

A tool to scrape and export your Dropbox activity history to CSV format for analysis and time tracking.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) - Install Docker Desktop for your operating system

## Quick Start

### 1. Capture Authentication Credentials

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
   ```bash
   docker run --name scraper_container scraper
   ```

4. **Export the output file**
   ```bash
   docker cp scraper_container:/scraper/output.csv ./output.csv
   ```

5. **Clean up (optional)**
   ```bash
   docker rm scraper_container
   ```

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

### No Events Returned

**Problem**: CSV file is empty or very small

**Possible causes**:
- Date range is outside your activity period
- The `timestamp` in the body parameter needs to be updated
- Check that your START_DATE is before END_DATE

### Rate Limiting

The scraper includes a 5-second delay between requests to avoid rate limiting. For large date ranges, the script may take several minutes to complete.

## Configuration Options

### Adjusting Batch Size

In `index.js`, you can modify:

```javascript
const PAGE_SIZE = 250  // Number of events per request (max: 250)
```

Larger values = fewer requests but higher risk of timeouts.

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
├── output.csv         # Generated output file
├── Dockerfile         # Docker configuration
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
- Maximum of 250 events per request
- Some events may not include `dataLink` if files were deleted
- Timestamps are in UTC (convert to local time in post-processing)

## Next Steps: Time Analysis

After scraping your data, use the Project Hours Analyzer to calculate time spent:

```bash
python project_hours_analyzer.py
```

See the [Project Hours Analyzer README](./project_hours_analyzer/README.md) for details.

## Contributing

Issues and pull requests are welcome! Please ensure:
- No sensitive data in commits
- Code follows existing style
- Test with your own Dropbox account first

## License

Apache-2.0 license - See LICENSE file for details

