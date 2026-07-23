const fetch = require("node-fetch");
const json2csv = require("json2csv");
const { htmlToText } = require('html-to-text');
const sleep = require('util').promisify(setTimeout);
const fs = require('fs');
const { decode } = require('./decoder.js');

let options
try {
    options = require("./options.json")
} catch (err) {
    console.error("Could not load options.json. In Docker, mount it with:")
    console.error("  docker run -v \"${PWD}/options.json:/scraper/options.json:ro\" ...")
    process.exit(1)
}

// Dropbox rejects anything above 100 with a 400 (the old 250 limit is gone)
const PAGE_SIZE = 100
const CSV_OUTPUT_PATH = process.env.CSV_OUTPUT_PATH || './output.csv'
const START_DATE = process.env.START_DATE || 'April 2, 2026 00:00:00 GMT+00:00'
const START_EPOCH_TIME = Math.round(new Date(START_DATE).getTime() / 1000)

const END_DATE = process.env.END_DATE || 'May 8, 2026 00:00:00 GMT+00:00'
const END_EPOCH_TIME = Math.round(new Date(END_DATE).getTime() / 1000)

if(isNaN(START_EPOCH_TIME) || isNaN(END_EPOCH_TIME)) {
    console.error("Invalid START_DATE or END_DATE. Use e.g. 'May 5, 2026 00:00:00 GMT+00:00'")
    process.exit(1)
}
let epochTime = END_EPOCH_TIME

// Track whether headers have been written
let headersWritten = false;

let replacer = () => {
    return "timestamp=" + epochTime.toString(10);
}

let getData = async () => {
    let date = new Date(0);

    options["body"] = options["body"].replace(/page_size=([\d]*)/, "page_size=".concat(PAGE_SIZE.toString(10)))
    options["body"] = options["body"].replace(/timestamp=([\d]*)/, replacer());
    date.setUTCSeconds(epochTime);
    console.log(date)

    let data = await fetch("https://www.dropbox.com/events/ajax", options);

    // Any non-2xx returns an HTML error page, so json() would throw something
    // unrecognisable. Surface the status instead.
    if(!data.ok) {
        throw new Error(data.status);
    }
    return data.json();
}

let getEventText = async (url) => {
    try {
        let optionsGetRequest = {...options}

        optionsGetRequest.method = 'GET'
        delete optionsGetRequest['body']

        let data = await fetch(url, optionsGetRequest)
        let html = await data.text()

        // Dropbox now emits window.addEdisonLoadCallback(Edison =>
        // Edison.registerStreamedPrefetch("blob"[, "blob"])). The old
        // edisonModule.Edison.* prefix is gone, and the payload moved to the
        // first argument, so match both positions.
        const regex = /registerStreamedPrefetch\(\s*"([^"]+)"(?:\s*,\s*"([^"]+)")?/g;
        let match;
        while ((match = regex.exec(html)) !== null) {
            for (const candidate of [match[1], match[2]]) {
                if(!candidate) continue

                let decodedData = ""
                try {
                    decodedData = decode(candidate)
                } catch (err) {
                    continue  // not every prefetch blob is a decodable payload
                }

                // Only a /pri/get/ link carries the file path the analyzer needs.
                // Returning the event_details URL instead would make it read the
                // event id as a project name and skip its own blurb fallback.
                if(decodedData.includes('/pri/get/')) {
                    console.log(decodedData)
                    return decodedData
                }
            }
        }
        return ""
    } catch(err) {
        console.error(err.message)
        return new Promise(resolve => resolve(""))
    }
}

let parseAndSave = async(data) => {
    return data.then(async data => {
        try {
            data.events = data.events.filter((eventDetail) => {
                return eventDetail['is_dup'] === false && eventDetail['timestamp'] >= START_EPOCH_TIME
            })

            for(const eventDetail of data.events) {
                let regex = /href='([^https:].*?)'/

                if (regex.exec(eventDetail['event_blurb']) != null) {
                    let dataLink = await getEventText("https://www.dropbox.com" + regex.exec(eventDetail['event_blurb'])[1])

                    eventDetail['dataLink'] = dataLink
                }
            }

            const fields = ['name', 'timestamp', 'ago', 'event_blurb', {
                label: 'blurb',
                value: (item) => {
                    return htmlToText(item['blurb'])
                }
            }, 'dataLink'];
            
            // Control header inclusion based on whether this is the first write
            const opts = {
                fields,
                header: !headersWritten  // Only include header if not yet written
            };

            const parser = new json2csv.Parser(opts);
            const csvData = parser.parse(data.events);
            let totalEvents = data.events.length

            console.log("Batch size: ", totalEvents)
            if(totalEvents === 0) {
                return -1;
            }

            epochTime = data.events[totalEvents - 1]['timestamp']

            // The first successful batch truncates any prior file; later batches
            // append. Truncating here (rather than deleting up front in main)
            // means a run that fails before its first batch - e.g. expired
            // cookies - leaves the previous output.csv intact.
            if (!headersWritten) {
                fs.writeFileSync(CSV_OUTPUT_PATH, csvData + '\n');
                headersWritten = true;
            } else {
                fs.appendFileSync(CSV_OUTPUT_PATH, csvData + '\n');
            }

            return 0;
        } catch (err) {
            console.error(err.message);
            throw err;
        }
    }).catch(err => {
       if(err.message == 403) {
           throw Error("Options.json seems outdated, authentication error")
       }
       if(err.message == 400) {
           throw Error("Dropbox rejected the request (400) - PAGE_SIZE above 100 is the usual cause")
       }
       // Never swallow: returning undefined here leaves epochTime unchanged and
       // the caller loops on the same batch forever
       throw err
    });
}

let main = async() => {
    // Reset headers flag when starting fresh. The output file is NOT cleared
    // here - the first successful batch truncates it (see parseAndSave), so a
    // run that dies before writing anything preserves the previous results.
    headersWritten = false;

    console.log("Writing to", CSV_OUTPUT_PATH)


    while (START_EPOCH_TIME < epochTime) {
        try {
            let previousEpochTime = epochTime
            let status = await parseAndSave(getData())

            if(status === -1) {
                break
            }

            // A batch that does not move the cursor means the next request is
            // identical: stop rather than loop on it forever
            if(epochTime === previousEpochTime) {
                throw Error("Cursor did not advance past " + epochTime + ", stopping")
            }

            await sleep(5000)
        } catch (err) {
            // epochTime holds the last successfully written batch boundary, so
            // report it: a long run that dies partway can resume from here
            let resumeFrom = new Date(0)
            resumeFrom.setUTCSeconds(epochTime)

            console.error("RUN FAILED at", new Date().toISOString(), "-", err.message)
            console.error("Rows up to", resumeFrom.toISOString(), "are in", CSV_OUTPUT_PATH)
            console.error("Resume with: -e END_DATE=\"" + resumeFrom.toUTCString() + "\"")
            process.exitCode = 1
            break
        }
    }
}

main().then(() => {
    if(process.exitCode === 1) {
        console.error("Run ended early - see the RUN FAILED lines above.")
        return
    }
    console.log("Fetched all the data.", new Date().toISOString())
})