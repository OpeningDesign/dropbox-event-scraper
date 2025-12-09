const fetch = require("node-fetch");
const json2csv = require("json2csv");
const { htmlToText } = require('html-to-text');
const sleep = require('util').promisify(setTimeout);
const fs = require('fs');
const { decode } = require('./decoder.js');

const options = require("./options.json")

const PAGE_SIZE = 250
const CSV_OUTPUT_PATH = './output.csv'
const START_DATE = 'September 01, 2025 20:00:00 GMT+00:00'
const START_EPOCH_TIME = Math.round(new Date(START_DATE).getTime() / 1000)

const END_DATE = 'December 08, 2025 21:59:59 GMT+00:00'
const END_EPOCH_TIME = Math.round(new Date(END_DATE).getTime() / 1000)
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
    if(data.status === 403) {
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

        const regex = /edisonModule\.Edison\.registerStreamedPrefetch\(\s*"([^"]+)"\s*,\s*"([^"]+)"/g;
        let match;
        while ((match = regex.exec(html)) !== null) {
            decodedData = decode(match[2])

            if(decodedData != "") {
                return new Promise(resolve => {
                    console.log(decodedData)
                    resolve(decodedData)
                })
            }
        }
        return new Promise(resolve => resolve(""))
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

            // Append to file
            fs.appendFileSync(CSV_OUTPUT_PATH, csvData);
            
            // Add newline after data if headers were written (to separate batches)
            if (!headersWritten) {
                fs.appendFileSync(CSV_OUTPUT_PATH, '\n');
                headersWritten = true;
            } else {
                fs.appendFileSync(CSV_OUTPUT_PATH, '\n');
            }

            return 0;
        } catch (err) {
            console.error(err.message);
        }
    }).catch(err => {
       if(err.message == 403) {
           throw Error("Options.json seems outdated, authentication error")
       }
    });
}

let main = async() => {
    // Reset headers flag when starting fresh
    headersWritten = false;
    
    fs.exists(CSV_OUTPUT_PATH, function(exists) {
        if(exists) {
            fs.unlinkSync(CSV_OUTPUT_PATH)
        }
    });
    
    while (START_EPOCH_TIME < epochTime) {
        try {
            let status = await parseAndSave(getData())

            if(status === -1) {
                break
            }

            await sleep(5000)
        } catch (err) {
            console.log(err.message)
            break
        }
    }
}

main().then(() => {
    console.log("Fetched all the data.")
})