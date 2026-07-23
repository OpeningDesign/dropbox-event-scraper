// Auto-refresh options.json by capturing a live /events/ajax request straight
// from Chrome, so you never have to do the DevTools "Copy as Node.js fetch"
// dance by hand.
//
//   npm run refresh
//
// To avoid a login/CAPTCHA every time, this seeds a private automation profile
// ONCE from your real Chrome profile (copying its logged-in Dropbox cookies).
// Modern Chrome (136+) refuses to let automation drive your Default profile in
// place, so we drive a copy instead. After the first seed it stays logged in
// and refreshes are zero-touch until Dropbox's session finally lapses.
//
// First run: close all Chrome windows so the profile can be copied. If cookies
// have gone stale, force a fresh copy with RESEED=1 (Chrome closed).
//
// Env overrides:
//   CHROME_PATH         path to chrome.exe (auto-detected otherwise)
//   CHROME_USER_DATA    your real "User Data" dir (auto-detected otherwise)
//   CHROME_PROFILE      which profile to copy from (default: Default)
//   REFRESH_PROFILE_DIR where the automation profile lives (default: home dir,
//                       kept OUT of this Dropbox-synced repo on purpose)
//   RESEED=1            re-copy cookies from your real profile
//
// Requires a local Chrome and the puppeteer-core dependency. Runs on the host.

const fs = require('fs');
const path = require('path');
const os = require('os');
const { execSync } = require('child_process');
const puppeteer = require('puppeteer-core');

const EVENTS_URL = 'https://www.dropbox.com/events';
const AJAX_MATCH = '/events/ajax';
const OPTIONS_PATH = path.join(__dirname, 'options.json');

// The automation profile deliberately lives outside the repo: the repo is inside
// a Dropbox folder, and a browser profile holds session cookies we don't want
// syncing to the cloud.
const PROFILE_DIR = process.env.REFRESH_PROFILE_DIR
    || path.join(os.homedir(), '.dropbox-event-scraper', 'chrome-profile');

const CAPTURE_TIMEOUT_MS = 4 * 60 * 1000;

const DROP_HEADERS = new Set(['host', 'content-length', 'accept-encoding', 'connection']);

// Cache/lock/crash dirs that are large or would confuse a copied profile.
const SKIP_ENTRIES = new Set([
    'Cache', 'Code Cache', 'GPUCache', 'DawnCache', 'DawnGraphiteCache',
    'GrShaderCache', 'ShaderCache', 'Service Worker', 'Crashpad',
    'component_crx_cache', 'extensions_crx_cache', 'BrowserMetrics', 'Safe Browsing',
]);

function findChrome() {
    if (process.env.CHROME_PATH && fs.existsSync(process.env.CHROME_PATH)) {
        return process.env.CHROME_PATH;
    }
    const candidates = [
        'C:/Program Files/Google/Chrome/Application/chrome.exe',
        'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
        path.join(process.env.LOCALAPPDATA || '', 'Google/Chrome/Application/chrome.exe'),
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/usr/bin/google-chrome',
    ];
    for (const c of candidates) {
        if (c && fs.existsSync(c)) return c;
    }
    throw new Error('Could not find Chrome. Set CHROME_PATH to its executable.');
}

function realUserDataDir() {
    if (process.env.CHROME_USER_DATA) return process.env.CHROME_USER_DATA;
    return path.join(process.env.LOCALAPPDATA || '', 'Google/Chrome/User Data');
}

function chromeRunning() {
    try {
        if (process.platform === 'win32') {
            const out = execSync('tasklist /FI "IMAGENAME eq chrome.exe" /NH', { encoding: 'utf8' });
            return /chrome\.exe/i.test(out);
        }
        execSync('pgrep -x chrome', { stdio: 'ignore' });
        return true;
    } catch (_) {
        return false;
    }
}

function copyFilter(src) {
    const base = path.basename(src);
    if (SKIP_ENTRIES.has(base)) return false;
    if (base.startsWith('Singleton')) return false; // stale locks -> "already running"
    if (base === 'lockfile') return false;
    return true;
}

// Copy the logged-in cookies (and the key that decrypts them) from the real
// Chrome profile into our automation profile's "Default".
function seedProfile() {
    const userData = realUserDataDir();
    const profile = process.env.CHROME_PROFILE || 'Default';
    const srcProfile = path.join(userData, profile);
    const srcLocalState = path.join(userData, 'Local State');

    if (!fs.existsSync(srcProfile)) {
        throw new Error('Real Chrome profile not found: ' + srcProfile
            + '\n  Set CHROME_USER_DATA and/or CHROME_PROFILE.');
    }
    if (chromeRunning()) {
        throw new Error('Chrome is running. Close ALL Chrome windows so the '
            + 'logged-in profile can be copied, then run "npm run refresh" again.');
    }

    fs.rmSync(PROFILE_DIR, { recursive: true, force: true });
    fs.mkdirSync(path.join(PROFILE_DIR, 'Default'), { recursive: true });

    // Local State carries the cookie-encryption key; app-bound encryption still
    // decrypts because we open the copy with the same chrome.exe.
    if (fs.existsSync(srcLocalState)) {
        fs.copyFileSync(srcLocalState, path.join(PROFILE_DIR, 'Local State'));
    }
    fs.cpSync(srcProfile, path.join(PROFILE_DIR, 'Default'), {
        recursive: true,
        filter: copyFilter,
    });
    console.log('Seeded automation profile from', srcProfile);
}

function cleanHeaders(raw) {
    const out = {};
    for (const [k, v] of Object.entries(raw)) {
        if (k.startsWith(':')) continue;
        if (DROP_HEADERS.has(k.toLowerCase())) continue;
        out[k] = v;
    }
    return out;
}

function captureAjax(client) {
    const pending = {};
    return new Promise((resolve) => {
        const finalize = async (id) => {
            const p = pending[id];
            if (!p || !p.extraHeaders || p.done) return;
            p.done = true;

            let body = p.request.postData;
            if (!body && p.request.hasPostData) {
                try {
                    body = (await client.send('Network.getRequestPostData', { requestId: id })).postData;
                } catch (_) { /* use what we have */ }
            }
            resolve({
                headers: { ...p.request.headers, ...p.extraHeaders },
                body,
                method: p.request.method,
            });
        };

        client.on('Network.requestWillBeSent', (e) => {
            if (e.request.method === 'POST' && e.request.url.includes(AJAX_MATCH)) {
                pending[e.requestId] = { request: e.request };
                finalize(e.requestId);
            }
        });
        client.on('Network.requestWillBeSentExtraInfo', (e) => {
            if (pending[e.requestId]) {
                pending[e.requestId].extraHeaders = e.headers;
                finalize(e.requestId);
            }
        });
    });
}

async function verify(options) {
    const probe = JSON.parse(JSON.stringify(options));
    probe.body = probe.body.replace(/page_size=\d+/, 'page_size=1');
    const r = await fetch('https://www.dropbox.com/events/ajax', probe);
    return r.status;
}

(async () => {
    const chromePath = findChrome();

    const needsSeed = process.env.RESEED === '1'
        || !fs.existsSync(path.join(PROFILE_DIR, 'Default', 'Network', 'Cookies'));
    if (needsSeed) {
        console.log('Seeding automation profile from your real Chrome login...');
        seedProfile();
    }

    console.log('Chrome   :', chromePath);
    console.log('Profile  :', PROFILE_DIR);

    const browser = await puppeteer.launch({
        headless: false,
        executablePath: chromePath,
        userDataDir: PROFILE_DIR,
        defaultViewport: null,
        // Strip automation fingerprints so Dropbox doesn't treat the window as a
        // bot (which makes its CAPTCHA re-serve forever even after you solve it).
        ignoreDefaultArgs: ['--enable-automation'],
        args: [
            '--no-first-run',
            '--no-default-browser-check',
            '--profile-directory=Default',
            '--disable-blink-features=AutomationControlled',
        ],
    });

    try {
        const page = (await browser.pages())[0] || await browser.newPage();
        await page.evaluateOnNewDocument(() => {
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        });

        const client = await page.target().createCDPSession();
        await client.send('Network.enable');
        const captured = captureAjax(client);

        await page.goto(EVENTS_URL, { waitUntil: 'domcontentloaded' }).catch(() => {});

        // A live session fires the feed request within a couple of seconds. Give
        // it a grace period before deciding a login is actually needed - checking
        // the URL immediately would catch Dropbox's transient /login redirect and
        // cry wolf even when the seeded cookies are fine.
        const capturedInTime = await Promise.race([
            captured.then(() => true),
            new Promise((res) => setTimeout(() => res(false), 10000)),
        ]);
        if (!capturedInTime) {
            if (page.url().includes('/login')) {
                console.log('\n>> Seeded cookies did not carry a live session.');
                console.log('   Log into Dropbox in the open window; capture continues automatically.');
                console.log('   (Tip: close Chrome and run "RESEED=1 npm run refresh" to recopy a fresh login.)\n');
            } else {
                console.log('Waiting for the events feed request...');
            }
        }

        const result = await Promise.race([
            captured,
            new Promise((_, rej) => setTimeout(
                () => rej(new Error('Timed out waiting for ' + AJAX_MATCH + '.')),
                CAPTURE_TIMEOUT_MS)),
        ]);

        const options = {
            headers: cleanHeaders(result.headers),
            body: result.body,
            method: result.method || 'POST',
        };
        if (!options.body || !/\bt=/.test(options.body) || !options.headers.cookie) {
            throw new Error('Captured request is missing body token or cookie - aborting.');
        }

        if (fs.existsSync(OPTIONS_PATH)) {
            fs.copyFileSync(OPTIONS_PATH, OPTIONS_PATH + '.bak');
            console.log('Backed up previous options.json -> options.json.bak');
        }
        fs.writeFileSync(OPTIONS_PATH, JSON.stringify(options, null, 2));
        console.log('Wrote', OPTIONS_PATH);

        const status = await verify(options);
        console.log('Verify   : POST /events/ajax ->', status, status === 200 ? '(OK)' : '(unexpected)');
        if (status !== 200) {
            console.log('Warning: expected 200. The scraper may still reject these credentials.');
        }
    } finally {
        await browser.close();
    }
})().catch((err) => {
    console.error('Refresh failed:', err.message);
    process.exit(1);
});
