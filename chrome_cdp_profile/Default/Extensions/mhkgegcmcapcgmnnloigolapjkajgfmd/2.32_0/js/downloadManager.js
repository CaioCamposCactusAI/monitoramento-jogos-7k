DownloadManager = function() {
    
    this.port = null;
    this.filterFileNameNeeded = true
    this.onCreate_listener = this.createListener.bind(this);
	this.onUpdate_listener = this.updateListener.bind(this);
    this.onErase_listener = this.eraseListener.bind(this);
    this.initialize();
}

DownloadManager.prototype.createListener = function(downloadItem) {

    var isReferrerNeeded = false;

    if( typeof(downloadItem.startTime) !== 'undefined' ) {
        var a = new Date(downloadItem.startTime);
        downloadItem.startTime = a.getTime();
    }
    //handling old donwload objects -> in downloadCreation's state has 'complete' or state has 'inter, then it is old download object
    if(downloadItem.state === 'complete' || downloadItem.state == 'interrupted')
    {
        // console.log("old donwload objects received");
        return;
    }
    if( typeof(downloadItem.endTime) !== 'undefined' ) {
        var a = new Date(downloadItem.endTime);
        downloadItem.endTime = a.getTime();
    }

    var allConditions = [
        !validateURL(downloadItem.referrer),
        !validateURL(downloadItem.url),
        !validateURL(downloadItem.finalUrl)
    ]


    //Handle blob URL
    downloadItem.url       = removePrefix(downloadItem.url, "blob:");   //No I18N
    downloadItem.referrer  = removePrefix(downloadItem.referrer, "blob:");  //No I18N
    downloadItem.finalUrl  = removePrefix(downloadItem.finalUrl, "blob:");  //No I18N

   var finalCondition = allConditions[0] && allConditions[1] && allConditions[2]
   
   if(finalCondition)
    {
        delete downloadItem.url
        delete downloadItem.referrer
        delete downloadItem.finalUrl
        
        this.sendURL(downloadItem.id, true, null)
    }
    else
    {
        if(allConditions[0])
        {
            // downloadItem.referrer = !allConditions[1]?downloadItem.url:downloadItem.finalUrl
            isReferrerNeeded = true;
        }
        if(allConditions[1])
        {
            downloadItem.url = !allConditions[2]?downloadItem.finalUrl:downloadItem.referrer
        }
        if(allConditions[2])
        {
            downloadItem.finalUrl = !allConditions[0]?downloadItem.referrer:downloadItem.url
        }
        this.sendURL(downloadItem.id, false, isReferrerNeeded ? "referrer" : null); //No I18N
    }

    this.port.postDownloadCreation(downloadItem, this.responseHandler.bind(this));

    //send filterFilename for firefox manually
    if(this.filterFileNameNeeded)
    {
        this.sendFilterFileName(downloadItem.id)
    }
}

DownloadManager.prototype.updateListener =  async function(downloadDelta) {
    if( typeof(downloadDelta.startTime) !== 'undefined' ) {
        var a = new Date(downloadDelta.startTime.current);
        downloadDelta.startTime.current = a.getTime();
    }
    if( typeof(downloadDelta.endTime) !== 'undefined' ) {
        var a = new Date(downloadDelta.endTime.current);
        downloadDelta.endTime.current = a.getTime();
    }
    
    if(downloadDelta.hasOwnProperty("referrer"))
    {
        if( downloadDelta.referrer.current == undefined ||[downloadDelta.referrer.current == "" || downloadDelta.referrer.current == null ||  downloadDelta.referrer.current.startsWith("data:")])
        {
            delete downloadDelta.referrer
        }
        else
        {
            downloadDelta.referrer = downloadDelta.referrer.current;
        }
    }
    if(downloadDelta.hasOwnProperty("finalUrl"))
    {
        if( [downloadDelta.finalUrl.current == undefined || downloadDelta.finalUrl.current == "" || downloadDelta.finalUrl.current == null || downloadDelta.finalUrl.current.startsWith("data:")])
        {
            delete downloadDelta.finalUrl
        }
        else
        {
            downloadDelta.finalUrl = downloadDelta.finalUrl.current;
        }
    }
    if(downloadDelta.hasOwnProperty("url"))
    {
        if( [downloadDelta.url.current == undefined || downloadDelta.url.current == "" || downloadDelta.url.current == null ||  downloadDelta.url.current.startsWith("data:")])
        {
            delete downloadDelta.url
        }
        else
        {
            downloadDelta.url = downloadDelta.url.current;
        }
    }

     //Retrive file size
    if (downloadDelta.hasOwnProperty("state") && downloadDelta.state.current === "complete") {  //NO I18N
        var res = await BROWSER.downloads.search({ id: downloadDelta.id });
        if (res && res.length > 0 && res[0].fileSize !== -1) {
            downloadDelta.fileSize = { current: res[0].fileSize };
        }

        this.port.postDownloadUpdate(downloadDelta, this.responseHandler.bind(this));
    } else {
        this.port.postDownloadUpdate(downloadDelta, this.responseHandler.bind(this));
    }
    
}

DownloadManager.prototype.eraseListener = function(downloadId) {
    this.port.postDownloadErase(downloadId);
}

DownloadManager.prototype.responseHandler = function(message) {
    if(message.action === "cancelDownload") {
        BROWSER.downloads.cancel(message.idToBeDeleted, this.cancelDownloadHandler.bind(this, message));
        let remove = BROWSER.downloads.removeFile(message.idToBeDeleted)
        remove.then(function success()
        {
            // console.log("success handle")
        }, function error(){
            // console.log("error handle")
        })
        BROWSER.downloads.erase({id:message.idToBeDeleted});
    }
}

DownloadManager.prototype.cancelDownloadHandler = function(message) {
    BROWSER.tabs.query({active: true, currentWindow: true}, function(tabs) {
        message.actiontype = "Download" //No I18N
        BROWSER.tabs.sendMessage(tabs[0].id, {"action":"cancelDownload","message":message});//No I18N
    });
}

DownloadManager.prototype.portConnected = function() {
    BROWSER.downloads.onCreated.addListener(this.onCreate_listener);
    BROWSER.downloads.onChanged.addListener(this.onUpdate_listener);
    BROWSER.downloads.onErased.addListener(this.onErase_listener);
}   

DownloadManager.prototype.initialize = function() {
    this.port = new Port(this.portConnected.bind(this), null, 2, this.downloadFilterListener.bind(this) );
}

DownloadManager.prototype.downloadFilterListener = function(flag) {
    //flag - true -> backward compatiblity for old executables //can be removed after SPs
    //flag - 1 -> enable both filename listner & download listner
    //flag - 2 -> enable only the download listner
    if(flag == true || flag == 1 || flag == 2) {
        if (BROWSER.downloads.onCreated.hasListener(this.onCreate_listener) == false) {
            BROWSER.downloads.onCreated.addListener(this.onCreate_listener);
        }
        if (BROWSER.downloads.onChanged.hasListener(this.onUpdate_listener) == false) {
            BROWSER.downloads.onChanged.addListener(this.onUpdate_listener);
        }
        if (BROWSER.downloads.onErased.hasListener(this.onErase_listener) == false) {
            BROWSER.downloads.onErased.addListener(this.onErase_listener);
        }
        //create a listener for download Filter file name fix.
        if(flag === 1)
        {
            this.filterFileNameNeeded = true
        }
        else
        {
            this.filterFileNameNeeded = false
        }
    }
    else
    {
        if (BROWSER.downloads.onCreated.hasListener(this.onCreate_listener) == true) {
            BROWSER.downloads.onCreated.removeListener(this.onCreate_listener);
        }
        if (BROWSER.downloads.onChanged.hasListener(this.onUpdate_listener) == true) {
            BROWSER.downloads.onChanged.removeListener(this.onUpdate_listener);
        }
        if (BROWSER.downloads.onErased.hasListener(this.onErase_listener) == true) {
            BROWSER.downloads.onErased.removeListener(this.onErase_listener);
        }
        this.filterFileNameNeeded = false
    }
}

//posting downloadupdate for base64 URLs
//allDetailsNeeded - true -> send only tabURL
//allDetailsNeeded - false -> send url, referrer, finalURL and tabURL
DownloadManager.prototype.sendURL =  async function(id, allDetailsNeeded,urlNeedfor) {
    var downloadDelta = {};
    downloadDelta.id = id;
    var info = await BROWSER.tabs.query({active: true,currentWindow: true})
    
    //check tabURL is proper
    if(info[0].url != undefined && !info[0].url.startsWith("data:") && info[0].url.length !== 0)
    {
        if(allDetailsNeeded)
        {
            downloadDelta.url = info[0].url;
            downloadDelta.finalUrl = info[0].url;
            downloadDelta.referrer = info[0].url;
            downloadDelta.tabURL = info[0].url;
        }
        else
        {
            if (urlNeedfor && typeof urlNeedfor === "string") {
                downloadDelta[urlNeedfor] = info[0].url;
            }

            downloadDelta.tabURL = info[0].url;

        }
    }
    // console.log(downloadDelta)
    if(Object.keys(downloadDelta).length > 1)
    {
        this.port.postDownloadUpdate(downloadDelta, this.responseHandler.bind(this))
    }
}

DownloadManager.prototype.sendFilterFileName = async function(id){
    var filename = await getFilterFileName(id);
   
    if(filename != null && filename != undefined && filename != "")
    {
        var fileInfo = {};
        fileInfo.id = id;
        fileInfo.filterFileName = filename;
        if(Object.keys(fileInfo).length > 1)
        {
            this.port.postDownloadUpdate(fileInfo, this.responseHandler.bind(this));
        }
    }
}

function removePrefix(value, prefix) {
    if (typeof value !== "string") {
        return value;
    }

    return value.startsWith(prefix)
        ? value.replace(prefix, "")
        : value;
}

function validateURL(url) {
    // Check for undefined or null first before trimming
    if (url == undefined || url == null) {
        return false;
    }
    
    url = url.trim();

    if (url == "" || url.startsWith("data:")) {
        return false;
    }
    
    // Check for blob: prefixes
    const validatePrefixes = ["blob:"]; //No I18N

    if (validatePrefixes.some(prefix => url.startsWith(prefix))) {
        if (gethostname(url, validatePrefixes) == null) {
            return false;
        }
    }

    return true;
}

//Function to get hostname after removing specified prefixes
function gethostname(url, prefixValidator) {
    
    for (let prefix of prefixValidator) {
        url = removePrefix(url, prefix);
    }

    try {
        var urlObj = new URL(url);
        return urlObj.hostname;
    } catch (e) {
        return null;
    }
}