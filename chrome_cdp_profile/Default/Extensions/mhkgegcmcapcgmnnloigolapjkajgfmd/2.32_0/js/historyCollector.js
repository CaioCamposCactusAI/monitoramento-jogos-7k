
HistoryCollector = function() {
    this.port = null;
    this.history_listener = this.historyVisitListener.bind(this);
    this.initialize();
}

HistoryCollector.prototype.historyVisitListener = function(HistoryItem) {

    //webHistory for Tab Details
    if (HistoryItem.tabId != -1 && this.port.webmetering) {
        if (!webHistory[HistoryItem.tabId]) {
            webHistory[HistoryItem.tabId] = {};
        }

        if (!webHistory[HistoryItem.tabId][HistoryItem.url]) {
            webHistory[HistoryItem.tabId] = {}; 	// for specific functionality
            webHistory[HistoryItem.tabId][HistoryItem.url] = {
                firstAccessed: HistoryItem.timeStamp,
                title: HistoryItem.title
            };

            let datatobepost = {};
            if (webHistory[HistoryItem.tabId]) {
                datatobepost = { ...webHistory[HistoryItem.tabId] };
                datatobepost.tabId = HistoryItem.tabId;
                datatobepost.internalcmd = "Update";    //No I18N
            } else {
                datatobepost.closedTime = Date.now();
                datatobepost.tabId = HistoryItem.tabId;
                datatobepost.internalcmd = "Update";    //No I18N
            }

            this.port.posttabWebHistoryUpdate(datatobepost, null);

        } else {
            console.log("webHistory send by onActivated Tab. No need to send again !!!");
            // webHistory[tabId][url].lastAccessed = tab.lastAccessed;
        }
    }
    //webHistory for Tab Details END
    
    var historyObject = {};
    var a = new Date(HistoryItem.timeStamp);
    historyObject.url = HistoryItem.url;
    try {
        const url = new URL(HistoryItem.url);
        const hostname = url.hostname ? url.hostname : "";
        const protocol = url.protocol ? url.protocol : "";
        if (hostname && protocol) {
           historyObject.domain = `${protocol}//${hostname}`;
        }
    } catch (err) {

    }
    historyObject.lastVisitTime = a.getTime();
    historyObject.title = "";
    this.port.postHistoryItem(historyObject, null);

}

HistoryCollector.prototype.initialize = function() {
    BROWSER.webRequest.onResponseStarted.addListener(
        this.history_listener,
        {urls: ['http://*/*', 'https://*/*'], types: ['main_frame']}	 //No I18N
    );
    this.port = new Port(null, null, 3, this.historyListener.bind(this));
}

HistoryCollector.prototype.historyListener = function(flag) {
    if(flag == true) 
    {
        if (BROWSER.webRequest.onResponseStarted.hasListener(this.history_listener) == false) {
            BROWSER.webRequest.onResponseStarted.addListener(
                this.history_listener,
                {urls: ['http://*/*', 'https://*/*'], types: ['main_frame']}	 //No I18N
            );
        }
    }
    else
    {
        if (BROWSER.webRequest.onResponseStarted.hasListener(this.history_listener) == true) {
            BROWSER.webRequest.onResponseStarted.removeListener(this.history_listener);
        }
    }

    setTitle("This extension tracks your web activity in compliance with your organization’s policy.",flag);   //No I18N

}

setTitle = function(title,flag) 
{
    if(flag)
    {
        BROWSER.action?.setTitle? BROWSER.action.setTitle({ title: title+"\n" })    //No I18N
        : BROWSER.browserAction.setTitle({ title: title }); //for Firefox
    }
    else
    {
        BROWSER.action?.setTitle? BROWSER.action.setTitle({ title: "" })    //No I18N
        : BROWSER.browserAction.setTitle({ title: "" });    //No I18N
    }
}
