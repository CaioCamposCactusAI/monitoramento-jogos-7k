WebMetering = function () {
    // Bind methods once
    this.onActivatedListener = this.onActivatedListener.bind(this);
    this.onRemovedListener = this.onRemovedListener.bind(this);
    this.onUpdatedListener = this.onUpdatedListener.bind(this);
    this.onWindowFocusChangedListener = this.onWindowFocusChangedListener.bind(this);


    this.initialize();
}

WebMetering.prototype.initialize = function () {
    this.port = new Port(this.portConnected.bind(this), null, 4, this.WebMeterListener.bind(this));
    webHistory = {}; // Clear global history on init
}

WebMetering.prototype.portConnected = function() {
    BROWSER.tabs.onActivated.addListener(this.onActivatedListener);
    BROWSER.tabs.onRemoved.addListener(this.onRemovedListener);
    BROWSER.tabs.onUpdated.addListener(this.onUpdatedListener);
    BROWSER.windows.onFocusChanged.addListener(this.onWindowFocusChangedListener);
}   


WebMetering.prototype.WebMeterListener = function (flag) {
    if (flag === true) {
        if (!BROWSER.tabs.onActivated.hasListener(this.onActivatedListener)) {
            BROWSER.tabs.onActivated.addListener(this.onActivatedListener);
        }
        if (!BROWSER.tabs.onRemoved.hasListener(this.onRemovedListener)) {
            BROWSER.tabs.onRemoved.addListener(this.onRemovedListener);
        }
        if (!BROWSER.tabs.onUpdated.hasListener(this.onUpdatedListener)) {
            BROWSER.tabs.onUpdated.addListener(this.onUpdatedListener);
        }
        if (!BROWSER.windows.onFocusChanged.hasListener(this.onWindowFocusChangedListener)) {
            BROWSER.windows.onFocusChanged.addListener(this.onWindowFocusChangedListener);
        }
    } else {
        if (BROWSER.tabs.onActivated.hasListener(this.onActivatedListener)) {
            BROWSER.tabs.onActivated.removeListener(this.onActivatedListener);
        }
        if (BROWSER.tabs.onRemoved.hasListener(this.onRemovedListener)) {
            BROWSER.tabs.onRemoved.removeListener(this.onRemovedListener);
        }
        if (BROWSER.tabs.onUpdated.hasListener(this.onUpdatedListener)) {
            BROWSER.tabs.onUpdated.removeListener(this.onUpdatedListener);
        }
        if (BROWSER.windows.onFocusChanged.hasListener(this.onWindowFocusChangedListener)) {
            BROWSER.windows.onFocusChanged.removeListener(this.onWindowFocusChangedListener);
        }
    }
}

WebMetering.prototype.onActivatedListener = function (activeInfo) {
    const tabId = activeInfo.tabId;
    BROWSER.tabs.get(tabId, (tab) => {
        if (BROWSER.runtime.lastError) return;
        this.updateWebHistoryFromTab(tabId, tab);
    });
}

WebMetering.prototype.onRemovedListener = function (tabId, removeInfo) {
    if (webHistory[tabId]) {
        delete webHistory[tabId];
    }
    this.postTabActivity(tabId, "Remove");  //No I18N
}

WebMetering.prototype.onUpdatedListener = function (tabId, changeInfo, tab) {
    if (changeInfo.status === "complete") {
        this.updateWebHistoryFromTab(tabId, tab);
    }
}

WebMetering.prototype.onWindowFocusChangedListener = function (windowId) {
    const focus_state = (windowId === -1) ? 0 : 1;
    const lastAccessed = Date.now(); // Epoch ms like GetDouble()

    const dataToPost = {
        internalcmd: "OnFocusChanged", // No I18N
        lastAccessed,
        focus_state
    };

    this.port.posttabWebHistoryUpdate(dataToPost, null);
};


WebMetering.prototype.updateWebHistoryFromTab = function (tabId, tab) {
    const url = tab.pendingUrl ?? tab.url;
    if (!url) return;

    if (!webHistory[tabId]) {
        webHistory[tabId] = {};
    }

    if (!webHistory[tabId][url]) {
        webHistory[tabId] = {}; // Reset existing entries for the tab
        webHistory[tabId][url] = {
            firstAccessed: tab.lastAccessed,
            title: tab.title
        };
    } else {
        webHistory[tabId][url].lastAccessed = tab.lastAccessed;
    }

    this.postTabActivity(tabId, "Update");  //No I18N
}

WebMetering.prototype.postTabActivity = function (tabId, internalcmd) {
    let dataToPost = {};
    if (webHistory[tabId]) {
        dataToPost = { ...webHistory[tabId], tabId, internalcmd };
    } else {
        dataToPost = {
            closedTime: Date.now(),
            tabId,
            internalcmd
        };
    }

    // const postPort = new Port(null, null, null, null);
    this.port.posttabWebHistoryUpdate(dataToPost, null);
}
