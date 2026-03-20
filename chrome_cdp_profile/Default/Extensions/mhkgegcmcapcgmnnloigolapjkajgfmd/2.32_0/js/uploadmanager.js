"use strict";   //No I18N
let z = []
let whitelisted = false;
let currentTabUrl = null;  

//Preprocess Upload check
let preUrlMatchCheck = false;
let sitesExcludeMatch = false;

function preprocessUploadCheck(ruleJSON) {
    //Use live URL for SPA sites where URL changes without page reload.
    currentTabUrl = getCurrentUrl(); 

    if(ruleJSON !== undefined && Object.keys(ruleJSON).length > 0){

        var blocklist = ruleJSON.uploadFilter.blocklist;
        let excludeList = ruleJSON.uploadFilter.excludeList;

        var data = {
            url: currentTabUrl,
        }
        
        if(blocklist.hasOwnProperty('sites') && blocklist.sites.length > 0){
            preUrlMatchCheck = matchRules("sites", blocklist.sites, data)   //No I18N
        }
        
        if(excludeList.hasOwnProperty('sites') && excludeList.sites.length > 0){
            sitesExcludeMatch = matchRules("sites", excludeList.sites, data);   //No I18N
        }
    }
}

//Helper: Get the current live URL (handles iframes and SPA navigation)
function getCurrentUrl() {
    return (window.location != window.parent.location) ? document.referrer : document.location.href;
}


function e(e) {
    chrome.runtime.sendMessage(e)
    z = [];
}

var custom_message = undefined;
var sendData = {};

function uploadBlockPost(e) {
    if(ruleJSON.uploadFilter.hasOwnProperty('custom_message') && (ruleJSON.uploadFilter.custom_message !== "" || ruleJSON.uploadFilter.custom_message !== null)){
        custom_message = ruleJSON.uploadFilter.custom_message;
    }
    if(ruleJSON.uploadFilter.hasOwnProperty("custom_logo") && (ruleJSON.uploadFilter.custom_logo !== "" || ruleJSON.uploadFilter.custom_logo !== null)){
        var logoUrl = ruleJSON.uploadFilter.custom_logo;
    }
    if(ruleJSON.uploadFilter.hasOwnProperty("custom_mail_id") && (ruleJSON.uploadFilter.custom_mail_id !== "" || ruleJSON.uploadFilter.custom_mail_id !== null)){
        var mailId = ruleJSON.uploadFilter.custom_mail_id;
    }

    sendData["actiontype"] = "UploadBlock"  //No I18N
    sendData["data"] = e    //No I18N
    sendData["custom_message"] = custom_message  //No I18N
    sendData["custom_logo"] = logoUrl    //No I18N
    sendData["custom_mail_id"] = mailId //No I18N

    chrome.runtime.sendMessage(sendData);
}

function uploadblock(eventType, event, data) {
    // z = [];
    switch (eventType) {
        case 0:
            // console.log("Upload Block Event : " + event);   //No I18N
            event.target.value = '';    //No I18N
            uploadBlockPost("Blocked"); //No I18N
            break;
        case 1:
            // console.log("Upload Block Event : " + event);    //No I18N
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            //Fake Event
            const fakeDropEvent = new Event('dragleave', {   //No I18N
                bubbles: true,
                cancelable: true
            });
            event.target.dispatchEvent(fakeDropEvent);
            uploadBlockPost("Blocked");  //No I18N
            break;
        case 2:
            // console.log("Upload Block Event : " + event);   //No I18N
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            //Fake Event -> Incase if needed Remove below commentout code
            // const fakePasteEvent = new Event('paste', {   //No I18N
            //     bubbles: true,
            //     cancelable: true
            // });
            // event.target.dispatchEvent(fakePasteEvent);
            uploadBlockPost("Blocked");   //No I18N
            break;
    }
}
function t(n) {
    var e = new Date(),
        t = null;
    do {
        t = new Date()
    } while (t - e < n)
}

function i(n, event,trigEvent) {
    try {
        let pendingMimes = 0;
        let completedMimes = 0;

        for (let i of n) {
            //folder
            let isDir = false;
            isDir = checkisDir(i,trigEvent);
            //folder
            const n = String(i.name);
            if (n) {
                let h = {};
                h.isDirectory = isDir;
                h.filename = isDir ? "folder" : n;  //No I18N
                h.fileSize = i.size;
                h.fileLastModified = i.lastModified;
                h.mime = i.type;
                h.UploadTime = Date.now();
                h.url = window.location.href;
                event.isFile = !0;
                z.push(h);

                pendingMimes++;
                // Async MIME detection
                getAccurateMime(i).then(accurateMime => {
                    // h.rawFileBytes = (accurateMime !== "unknown/unknown") ? accurateMime : i.type; //No I18N
                    if (accurateMime !== "unknown/unknown") {
                        h.rawFileBytes = accurateMime; // Only add if valid
                    }
                    completedMimes++;

                    if (completedMimes === pendingMimes) {
                        e(z); //post to nativehost
                    }
                });
            }
        }
    } catch (n) {
        event.isFile = !1, t = ""   //No I18N
    }
}

function a(event) {
    if (event.target.files && event.target.files.length > 0) {
        z = []; 
        sendData = {};
        let o = { isFile: !1 };
        i(event.target.files, o,"change");  //No I18N
        let match = evaluateRuleJSON(z);
        if (match) {
            uploadblock(0, event, 0);
        } else {
            //Below code is commented out to avoid sending data instead of we post in function (i & o)
            // if (o.isFile) {
            //     z.length > 0 && (e(z), t(500));
            // }
        }
    }
}

function evaluateRuleJSON(uploadData) {
    let match = false;

    if(ruleJSON == undefined || Object.keys(ruleJSON).length === 0){
        // console.log("No rules defined, allowing upload by default.");  //No I18N
        return match; // No rules defined, allow upload by default
    }

    //Re-evaluate URL match on every upload for SPA sites where URL changes
    //without page reload. Previously preUrlMatchCheck was computed only at initialization.
    refreshUrlMatchForSPA(ruleJSON);

    //Block All Uploads
    if (ruleJSON.uploadFilter.block_all_uploads === "1") {
        return true; // Block all uploads
    }
    let rules_json = ruleJSON.uploadFilter; //uploadFilter
    let blocklist = rules_json.blocklist;
    let folderAllow = rules_json.folder;
    let excludeList = rules_json.excludeList;
    let whitelist = rules_json.whitelist;
    whitelisted = whitelist;
    let all_condition_match = rules_json.all_condition_match;

    //Create a local copy of file_types to avoid mutating ruleJSON on every call.
    //Previously, folderAllow was pushed to the original blocklist.file_types array on every
    //upload event, causing the array to grow indefinitely.
    let blocklistFileTypes = blocklist.hasOwnProperty('file_types') ? [...blocklist.file_types] : undefined;

    uploadData.some(data => {

        if (blocklistFileTypes && rules_json.hasOwnProperty('folder') && (!blocklistFileTypes.some(item => typeof item === 'object' && 'folderAllow' in item))) {    //No I18N
            blocklistFileTypes.push({ folderAllow: folderAllow == "true" ? true : false });  //No I18N
        }
            
        if(!sitesExcludeMatch) {

            if (all_condition_match) {
                var Conditions = [
                    blocklist.range != undefined ? matchRules("range", blocklist.range, data) : true,   //No I18N
                    // blocklist.sites.length > 0 ? matchRules("sites", blocklist.sites, data) : true,  //No I18N
                    blocklist.sites.length > 0 ? preUrlMatchCheck : true,
                    blocklistFileTypes != undefined ? matchRules("file_types", blocklistFileTypes, data) : true,    //No I18N
                    blocklist.file_size != undefined && !data.isDirectory ? matchRules("file_size", blocklist.file_size, data) : true    //No I18N
                ];

                match = Conditions.every(condition => condition === true);

                /*if(match && whitelist){
                    match = false;
                }
                else if(!match && whitelist){
                    match = true;
                }*/
                // match = matchRules("folder_allow",folderAllow,data) && matchRules("range", blocklist.range, data) && matchRules("sites", blocklist.sites, data) && matchRules("file_types", blocklist.file_types, data) && matchRules("file_size", blocklist.file_size, data);  //No I18N
            }
            else {
                var Conditions = [
                    blocklist.range != undefined ? matchRules("range", blocklist.range, data) : false,  //No I18N
                    // blocklist.sites.length > 0 ? matchRules("sites", blocklist.sites, data) : false,    //No I18N
                    blocklist.sites.length > 0 ? preUrlMatchCheck : false,
                    blocklistFileTypes != undefined ? matchRules("file_types", blocklistFileTypes, data) : false,   //No I18N
                    blocklist.file_size != undefined && !data.isDirectory ? matchRules("file_size", blocklist.file_size, data) : false   //No I18N
                ];

                match = Conditions.some(condition => condition === true);

                /*if(match && whitelist){
                    match = false;
                }
                else if(!match && whitelist){
                    match = true;
                }*/
                // match = matchRules("folder_allow",folderAllow,data) || matchRules("range", blocklist.range, data) || matchRules("sites", blocklist.sites, data) || matchRules("file_types", blocklist.file_types, data) || matchRules("file_size", blocklist.file_size, data);  //No I18N
            }
        }

        /*if (match) {
            // console.log("Before check Exclude Sites All Conditions are matched  in evaluateRuleJSON : " + match);   //No I18N
            match = !matchRules("sites", excludeList.sites, data);  //No I18N
            // console.log("After Check Exclude sites All Conditions are matched  in evaluateRuleJSON : " + match);    //No I18N
            return match;
        }*/
       if(whitelist){
            match = !match;
       }
    });
    
    return match;

}

function matchRules(rulename, rule, uploadData) {

    switch (rulename) {
        case 'range':   //No I18N
            return checkTime(rule);
        case 'sites':   //No I18N
            return checkUrl(rule);
        case 'file_types':  //No I18N
            return checkFileType(rule);
        case 'file_size':   //No I18N
            return checkFileSize(rule);
        default:
            return false;
    }


    function checkTime(rule) {
        const currentTime = new Date().toTimeString().split(' ')[0];
        const [startTime, endTime] = rule;
        // alert(currentTime+" == "+startTime);
        var value = currentTime >= startTime && currentTime <= endTime;
        // console.log("Time Match : " + value);   //No I18N
        if(value){
            sendData["time"] = `${startTime} to ${endTime}`;
        }
        return currentTime >= startTime && currentTime <= endTime;
    }

    function checkUrl(rule) {
        let urlMatch = false;
        rule.some(site => {
            //Return Match if any of the URL matches
            // urlMatch = uploadData.tabURL.includes(site) || uploadData.referrer.includes(site) || uploadData.url.includes(site) || uploadData.finalUrl.includes(site);
            urlMatch =  uploadData.url.includes(site);
            if (urlMatch) {
                // console.log("URL Match : " + urlMatch); //No I18N
                sendData["domain"] = site;
                return urlMatch;
            }
        });
        return urlMatch;
    }

    function checkFileType(rule) {
        let actualFileType = getFileType(uploadData.filename);
        let fileTypeMatch = rule.includes(actualFileType);
        if(fileTypeMatch){
            sendData["filetype"] = actualFileType
        }

        let folderAllow = rule.find(item => typeof item === 'object' && 'folderAllow' in item)?.folderAllow;

        if (folderAllow != undefined) {
            
            if((!folderAllow && uploadData.isDirectory) || (folderAllow && uploadData.isDirectory && whitelisted)){
                fileTypeMatch = true;
                sendData["filetype"] = "folder" //No I18N
            }
        }
        return fileTypeMatch;
    }

    function checkFileSize(rule) {
        const { size, greater } = rule;
        let fileSize = uploadData.fileSize;
        
        if (greater) {
            // console.log("File Size Match : " + (fileSize > size));  //No I18N
            if(fileSize > size){
                sendData["filesize"] = fileSize;
            }
            return fileSize > size;
        } else {
            if(fileSize < size){
                sendData["filesize"] = fileSize
            }
            return fileSize < size;
        }
    }



    function getFileType(file) {
        let filetype = file.split('.').pop();
        return filetype;
    }

}

function checkisDir(item,event)
{
    let isDir = false;
    if(event==="change")    //No I18N
    {
        if (item.webkitRelativePath && item.webkitRelativePath.includes("/")) { //No I18N
            isDir = true;
        } 
    }

    if(event==="drop")
    {
        let webkitdata;
        if (item instanceof DataTransferItem) {
            webkitdata = item.webkitGetAsEntry();
        } else {
            webkitdata = item;
        }
        if (webkitdata) {
            if(webkitdata.isDirectory){
                isDir = true;
            }
        }
    }

    if (event === "filefolderpicker") {   // showOpenFilePicker
        // Always files, no directory support here
        if(item.hasOwnProperty("type") && item.type === "folder")
        {
            isDir = true;
        } else{
            isDir = false;
        }
    }
    return isDir;
}


function o(items) {

    let pendingMimes = 0;
    let completedMimes = 0;

    for (let t = 0; t < items.length; t++) {
        let item = items[t];
        let isDir = false;
        isDir = checkisDir(item,"drop");    //No I18N

        if (item.kind === "file" || isDir) {    //No I18N
            let file = item.getAsFile();
            if (file) {

                let h = {
                    isDirectory: isDir,
                    filename: file.name,
                    fileSize: file.size,
                    fileLastModified: file.lastModified,
                    mime: file.type,
                    UploadTime: Date.now(),
                    url: window.location.href,
                };
                z.push(h);

                pendingMimes++;
                // Async MIME detection
                getAccurateMime(file).then(accurateMime => {
                    // h.rawFileBytes = (accurateMime !== "unknown/unknown") ? accurateMime : file.type;   //No I18N
                    if (accurateMime !== "unknown/unknown") {
                        h.rawFileBytes = accurateMime; // Only add if valid
                    }
                    completedMimes++;

                    if (completedMimes === pendingMimes) {
                        e(z);
                    }
                });
            }
        }
    }
    // console.log("Items Processed: ", z);  //No I18N

    return null;
}

function getFileFromEntry(fileEntry) {  //async function
    return new Promise((resolve, reject) => {
        fileEntry.file(resolve, reject);
    });
}

function r(event) {
    try {
        z = [];
        sendData = {};
        const items = event.dataTransfer.items;
        o(items);

        let match = evaluateRuleJSON(z);
        if (match) {
            uploadblock(1, event, 0);
        } else {
            if (z.length > 0) {
                // e(z);
            }
        }
    }
    catch (e) {
        // console.log("Error in Drag Event : " + e);  //No I18N
    }
}

function p(event) {
    if (event.clipboardData.files && event.clipboardData.files.length > 0) {
        z = [];
        sendData = {};
        let o = {
            isFile: !1
        };
        i(event.clipboardData.files, o,"paste");    //No I18N
        let match = evaluateRuleJSON(z);
        if (match) {
            uploadblock(2, event, 0);
        } 
        // else {
            // if (o.isFile) {
            //     z.length > 0 && (e(z), t(500));
            // }
        // }
    }
}

//MIME Type POC

function getAccurateMime(file) {
    return new Promise((resolve) => {
        try {
            const safeFile = new Blob([file]);
            const reader = new FileReader();

            reader.onloadend = function (e) {
                try {
                    if (!e.target.result) {
                        return resolve("unknown/unknown");   //No I18N
                    }

                    const arr = new Uint8Array(e.target.result).subarray(0, 16);
                    let hexArray = [];
                    for (let i = 0; i < arr.length; i++) {
                        hexArray.push("0x" + arr[i].toString(16).padStart(2, "0").toUpperCase());
                    }

                    resolve(hexArray.length > 0 ? hexArray.join(", ") : "unknown/unknown"); //No I18N
                } catch (err) {
                    resolve("unknown/unknown"); // fallback  //No I18N
                }
            };

            reader.onerror = function (err) {
                resolve("unknown/unknown");  //No I18N
            };

            reader.readAsArrayBuffer(safeFile.slice(0, 16));
        } catch (err) {
            console.error("Permission denied or invalid file access:", err); //No I18N
            resolve("unknown/unknown");  //No I18N
        }
    });
}

var ruleJSON = {};
var uploadTracking = false;

function s(rules_json) {
    ruleJSON = rules_json;
    attachListeners(document);
    filefolderListener();
    ShadowDomListener();
}

function attachListeners(doc) {
    doc.addEventListener("change", a, true); //No I18N
    doc.addEventListener("drop", r, true);    //No I18N
    doc.addEventListener("paste", p, true);   //No I18N
}

function ShadowDomListener() {
    const processedRoots = new WeakSet();
    const observedRoots = new WeakSet();

    // Attach a MutationObserver inside each shadow root so we catch
    // child web-components that are created asynchronously (e.g. Lit/Polymer rendering).
    // Without this, scanShadowRoots runs once and misses children rendered after a delay.
    const observeShadowRoot = (shadowRoot) => {
        if (observedRoots.has(shadowRoot)) return;
        observedRoots.add(shadowRoot);

        const shadowObserver = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType !== Node.ELEMENT_NODE) return;
                    try {
                        scanShadowRoots(node);
                    } catch (e) {
                        // Silently handle errors
                    }
                });
            });
        });

        shadowObserver.observe(shadowRoot, {
            childList: true,
            subtree: true
        });
    };

    //Listen for synchronous DOM events from closed shadow roots intercepted by shadowhook.js.
    //shadowhook.js (MAIN world) writes file metadata to data-bsp-req, dispatches 'bsp-shadow-eval',
    //and we write the decision to data-bsp-dec. Since dispatchEvent is synchronous, the decision
    //is available to shadowhook.js in the SAME event tick — before any page handler fires.
    //uploadmanager.js remains the sole decision maker (no duplicated rule logic).
    document.documentElement.addEventListener('bsp-shadow-eval', () => {   //No I18N
        try {
            var root = document.documentElement;
            var raw = root.getAttribute('data-bsp-req');   //No I18N
            if (!raw) return;

            var req = JSON.parse(raw);
            z = [];
            sendData = {};
            const fakeFiles = req.files.map(f => ({
                name: f.name,
                size: f.size,
                type: f.type,
                lastModified: f.lastModified,
                webkitRelativePath: ''  //No I18N
            }));
            let o = { isFile: false };
            i(fakeFiles, o, "change");  //No I18N
            let match = evaluateRuleJSON(z);

            // Write decision to DOM attribute — shadowhook.js reads this synchronously
            root.setAttribute('data-bsp-dec', match ? 'block' : 'allow');   //No I18N

            if (match) {
                uploadBlockPost("Blocked");  //No I18N
            }
        } catch (e) {
            // On error, write allow so the file isn't silently eaten
            try {
                document.documentElement.setAttribute('data-bsp-dec', 'allow');   //No I18N
            } catch(e2) {}
        }
    });

    // No maxDepth — recurse as deep as shadow roots exist
    const scanShadowRoots = (node) => {
        if (!node) return;
        try {
            let shadow = node.shadowRoot;
            if (shadow && !processedRoots.has(shadow)) {
                processedRoots.add(shadow);

                shadow.addEventListener("change", a, true);  //No I18N
                shadow.addEventListener("drop", r, true);    //No I18N
                shadow.addEventListener("paste", p, true);   //No I18N

                // Watch this shadow root for future child additions (async rendering)
                observeShadowRoot(shadow);

                // Recurse into shadow root children
                shadow.querySelectorAll('*').forEach(el => scanShadowRoots(el));
            }
            // Recurse into regular children to find nested shadow roots
            if (node.children) {
                for (let child of node.children) {
                    scanShadowRoots(child);
                }
            }
        } catch (e) {
            // Silently handle errors
        }
    };

    // Initial scan of existing DOM
    try {
        scanShadowRoots(document.body);
    } catch (e) {
        // Silently handle errors
    }

    // Single unified MutationObserver for the light DOM
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            mutation.addedNodes.forEach((node) => {
                if (node.nodeType !== Node.ELEMENT_NODE) return;
                try {
                    // Handle iframes
                    if (node.contentDocument !== undefined) {
                        node.addEventListener('load', () => {
                            
                            let doc = node.contentDocument;
    
                            if (!doc) {
                                // wrapped in try/catch because contentWindow.document throws SecurityError on cross-origin
                                try {
                                    doc = node.contentWindow && node.contentWindow.document;
                                } catch (e) {
                                    // Cannot access cross-origin iframe
                                }
                            }

                            if (doc) {
                                attachListeners(doc);
                                if (doc.body) scanShadowRoots(doc.body);
                            }
                        });
                    }
                    // Scan for shadow roots in the newly added node
                    scanShadowRoots(node);
                } catch (e) {
                    // Silently handle cross-origin errors
                }
            });
        });
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
}

function filefolderListener(){
    // Listen for messages from page script
    window.addEventListener("message", (event) => {
        if (event.source !== window) return;
        const msg = event.data;

        if (msg && msg.source === "file-picker-hook") { //No I18N

            z = [];
            sendData = {};
            const fakeFileList = msg.files.map(f => ({
            name: f.name,
            size: f.size,
            type: f.type,
            lastModified: f.lastModified
            }));

            let o = { isFile: false };
            i(fakeFileList, o, "filefolderpicker"); //No I18N
            let match = evaluateRuleJSON(z);

            // Always reply with decision
            window.postMessage({
                source: "file-picker-decision", //No I18N
                requestId: msg.requestId,
                block: match
            }, currentTabUrl);

            if (match) {
            uploadblock(0, event, 0);
            }
        }
    }, false);
}


// Re-evaluate URL-based rules on every upload event for SPA sites.
//On SPAs the URL changes via History API without page reload, so the initial
//preUrlMatchCheck / sitesExcludeMatch may become stale.
function refreshUrlMatchForSPA(ruleJSON) {
    var liveUrl = getCurrentUrl();
    if (liveUrl !== currentTabUrl) {
        currentTabUrl = liveUrl;
        preUrlMatchCheck = false;
        sitesExcludeMatch = false;

        var blocklist = ruleJSON.uploadFilter.blocklist;
        var excludeList = ruleJSON.uploadFilter.excludeList;
        var data = { url: currentTabUrl };

        if (blocklist.hasOwnProperty('sites') && blocklist.sites.length > 0) {
            preUrlMatchCheck = matchRules("sites", blocklist.sites, data);   //No I18N
        }
        if (excludeList.hasOwnProperty('sites') && excludeList.sites.length > 0) {
            sitesExcludeMatch = matchRules("sites", excludeList.sites, data);   //No I18N
        }
    }
}

// Initialize content script
chrome.runtime.sendMessage({
    "Request": "UploadCheck"    //No I18N
}, function (e) {
    uploadTracking = e.s;  
    if (Object.keys(e.rule_json).length > 0 || uploadTracking) {
        preprocessUploadCheck(e.rule_json);
        s(e.rule_json);
    }
});