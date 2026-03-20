var webRequestListenerCallback;			//1
var downloadFilterListenerCallback;		//2
var historyListenerCallback;			//3
var webmeterListenerCallback;			//4

Port = function(connect_callback, disconnect_callback, callingFunction,listener_callback ) {
	switch(callingFunction){
		case 1:
			webRequestListenerCallback = listener_callback.bind(this);
			break;
		case 2:
			downloadFilterListenerCallback = listener_callback;
			break;
		case 3:
			historyListenerCallback = listener_callback;
			break;
		case 4:
			webmeterListenerCallback = listener_callback;
			break;
	}

	if (typeof Port.instance === 'object') {
		if(connect_callback) {
			connect_callback();
		}
		return Port.instance;
	}

	this.MAX_CONNECT_ATTEMPTS = 5;
	this.port = null;
	this.callbacks = [];
	this.next_id = 1;
	this.connect_attempts_left = this.MAX_CONNECT_ATTEMPTS;
	this.last_connect_time = 0;
	this.connect_callback = connect_callback;
	this.disconnect_callback = disconnect_callback;
	this.check_upload = true;//for mac platform, we need to keep this as true
	this.ruleJSON = {};
	this.webmetering = false;
	this.filePickerNotNeeded = false;
	this.tabUpdationListner = this.tabUpdationListerCallback.bind(this);

	Port.instance = this;

	this.initialize();
};


 Port.prototype.initialize = function() {
 	var self = this;
 	self.port = BROWSER.runtime.connectNative('com.manageengine.browserrouter'); //No I18N
 	if (BROWSER.runtime.lastError) {
 		console.error(BROWSER.runtime.lastError.message);
 		self.port = null;
 		self.disconnect_callback();
 		return;
 	}
 	self.port.onMessage.addListener(self.onMessageReceived.bind(self));
 	self.port.onDisconnect.addListener(function() {
 		console.error('Lost connection to the native host: ' + //No I18N
			 BROWSER.runtime.lastError.message);
		// if(BROWSER.runtime.lastError.message === "Specified native messaging host not found.") {
		// 	window.open("https://www.manageengine.com/secure-browser/",'_blank');
		// 	self.connect_attempts_left = 0;
		// }
 		self.port = null;
 		if (--self.connect_attempts_left > 0) {
 			setTimeout(self.initialize.bind(self), 3000);
 			return;
 		}
 		self.disconnect_callback();
 	});
 	try {
 		self.logError('Ignore me.', self.connect_callback); //No I18N
 	} catch (err) {
 		self.port = null;
 	}
 };

 Port.prototype.onMessageReceived = function(message) {
 	console.log("Message received: " + JSON.stringify(message)); //No I18N
 	if (!message.success) {
 		console.error('Command Nr.' + message.id + ' failed:' + message.error); //No I18N
 	}
 	if (message.id !== 0) {
 		this.callbacks[message.id](message);
 		delete this.callbacks[message.id];
 	} else {
		if (message.action === "Uninstall") {
 			this.connect_attempts_left = 0;
 			console.log("Uninstall command received, so not going to reconnect to native host");
 		}
		else if(message.action === "PolicyRefresh")
		{
			//callbacks
			if(message.hasOwnProperty("WebRequest"))
			{
				webRequestListenerCallback(message.WebRequest);
			}
			if(message.hasOwnProperty("History"))
			{
				historyListenerCallback(message.History);
			}	
			if(message.hasOwnProperty("DownloadFilter"))
			{
				downloadFilterListenerCallback(message.DownloadFilter);
			}

			//enable based on flags
			if(message.hasOwnProperty("WebMetering"))
			{
				this.webmetering = message.WebMetering;
			}
			else
			{
				this.webmetering = false; //currently this is optional feature so disabling it
			}
			webmeterListenerCallback(this.webmetering);
			if(message.hasOwnProperty("UploadFilter"))
			{
				this.check_upload = message.UploadFilter;
			}
			if(message.hasOwnProperty("ruleJSON"))
			{
				this.ruleJSON = message.ruleJSON;
			}
			if(message.hasOwnProperty("RemoveFilePicker"))
			{
				this.filePickerNotNeeded = message.RemoveFilePicker
			}

			this.UploadHelper()
		}
		else if(message.action === "Upgrade"){
			console.log("Upgrade Command Received, going to re - initialize the connectattempts");
			
			setTimeout(() => {  
				this.connect_attempts_left = 5;	
			}, 5000);
		}
		else if(message.action === "StartupURLsandNewTab") {
			HandleStarupSetting(message)
		}
 	}
 };


 Port.prototype.checkPortState = function(callback) {
 	if (!this.port) {
 		if (callback) {
 			callback({ success: false, error: 'No native connection!' }); //No I18N
 		}
 		return false;
 	}
 	return true;
 };


 Port.prototype.registerCallback = function(callback) {
 	var id = 0;
 	if (callback) {
 		id = this.next_id;
 		this.callbacks[id] = callback;
 		this.next_id++;
 	}
 	return id;
 };


 Port.prototype.logError = function(error, callback) {
 	if (!this.checkPortState(callback)) {
 		return;
 	}
	console.log("Posting LogError : " + JSON.stringify(error) + " connectAttemptsLeft :" +  JSON.stringify(this.connect_attempts_left));

 	this.port.postMessage({
 		'id': this.registerCallback(callback), //No I18N
 		'command': 'logError', //No I18N
 		'error': error,	//No I18N
 		'connectAttemptsLeft' : this.connect_attempts_left //No I18N
 	}); //No I18N
 };

 Port.prototype.invokeRouter = function(url, tabId, callback) {
 	if (!this.checkPortState(callback)) {
 		return;
 	}
 	this.port.postMessage({
 		'id': this.registerCallback(callback), //No I18N
 		'command': 'invokeRouter', //No I18N
 		'url': url, //No I18N
 		'tabId': tabId	//No I18N
 	}); //No I18N
 };

 Port.prototype.redirectedRequestRouter = function(url, tabId, oldUrl, callback) {
 	if (!this.checkPortState(callback)) {
 		return;
 	}
	console.log("Posting RedirectedRequestRouter url  : " + JSON.stringify(url) + " tabId : " + JSON.stringify(tabId) + " oldUrl : " + JSON.stringify(oldUrl));

 	this.port.postMessage({
 		'id': this.registerCallback(callback), //No I18N
 		'command': 'redirectedRequestRouter', //No I18N
 		'url': url, //No I18N
 		'tabId': tabId, //No I18N
 		'oldUrl': oldUrl	//No I18N
 	}); //No I18N
 };

 Port.prototype.updateExtensionInventory = function(necessaryInfo, callback) {
 	if (!this.checkPortState(callback)) {
 		return;
 	}
	console.log("Posting UpdateExtensionInventory : " + JSON.stringify(necessaryInfo));

 	this.port.postMessage({
 		'id': this.registerCallback(callback), //No I18N 
 		'command': 'updateExtensionInventory', //No I18N
 		'extensionData': necessaryInfo	//No I18N
 	}); //No I18N
 };

 Port.prototype.postInstallExtensionInventory = function(extDetails, callback) {
 	if (!this.checkPortState(callback)) {
 		return;
 	}
	console.log("Posting PostInstallExtensionInventory : " + JSON.stringify(extDetails));

 	this.port.postMessage({
 		'id': this.registerCallback(callback), //No I18N
 		'command': 'postInstallExtensionInventory', //No I18N
 		'extensionDataArray': extDetails	//No I18N
 	}); //No I18N
 };

 Port.prototype.postBrowserSettings = function(browserSettings, callback) {
	if (!this.checkPortState(callback)) {
		return;
	}
	console.log("Posting PostBrowserSettings : " + JSON.stringify(browserSettings));

	this.port.postMessage({
		'id': this.registerCallback(callback), //No I18N
		'command': 'postBrowserSettings', //No I18N
		'browserSettings': browserSettings	//No I18N
	}); //No I18N
};
 
Port.prototype.postHistoryItem = function(historyObject, callback) {
	if (!this.checkPortState(callback)) {
		return;
	}
	this.port.postMessage({
		'id': this.registerCallback(callback), //No I18N
		'command': 'postHistoryItem', //No I18N
		'historyObject': historyObject	//No I18N
	}); //No I18N
}

Port.prototype.postDownloadCreation = function(downloadObject, callback) {
	if (!this.checkPortState(callback)) {
		return;
	}
	console.log("Posting PostDownloadCreation : " + JSON.stringify(downloadObject));

	this.port.postMessage({
		'id': this.registerCallback(callback), //No I18N
		'command': 'downloadCreation', //No I18N
		'downloadObject': downloadObject	//No I18N
	}); //No I18N
}

Port.prototype.postDownloadUpdate = function(downloadDelta, callback) {
	if (!this.checkPortState(callback)) {
		return;
	}
	console.log("Posting PostDownloadUpdate : " + JSON.stringify(downloadDelta));

	this.port.postMessage({
		'id': this.registerCallback(callback), //No I18N
		'command': 'downloadUpdate', //No I18N
		'downloadDelta': downloadDelta	//No I18N
	}); //No I18N
}

Port.prototype.postDownloadErase = function(downloadId, callback) {
	if (!this.checkPortState(callback)) {
		return;
	}
	console.log("Posting PostDownloadErase : " + JSON.stringify(downloadId));

	this.port.postMessage({
		'id': this.registerCallback(callback), //No I18N
		'command': 'downloadErase', //No I18N
		'downloadId': downloadId	//No I18N
	}); //No I18N
}

Port.prototype.postUploadData = function(UploadObject, tabId, url, callback) {
	if (!this.checkPortState(callback)) {
		return;
	}
	//Remove Unused property from UploadObject
	UploadObject.forEach(obj => {
		if(obj.hasOwnProperty("isDirectory")){
			delete obj.isDirectory;
		}
    });
	this.port.postMessage({
		'id': this.registerCallback(callback), //No I18N
		'command': 'UploadData', //No I18N
		'UploadObject': UploadObject, //No I18N
		'url': url, 				  //No I18N
		'uploadTime': Date.now(), //No I18N
 		'tabId': tabId	//No I18N
	});
}

async function HandleStarupSetting(message){
	//chrome opens startup URLs even at any Inspect window | Incognito window is open : Need to implement the same. Now due to service worker sleep & wakeup, it opens page randomly, we only do at browser startup
	if(isBrowserStartup)
	{
		if(message.startupURLs !== undefined)
		{
			const urls = message.startupURLs
			let tabs = await BROWSER.tabs.query({})
		
			await tabs.forEach(async tab => {
				if(isNewTab(tab))
				{
					if(urls[0].indexOf("://") == -1)
					{
						urls[0] = "https://" + urls[0];
					}
					BROWSER.tabs.update(tab.id, {url:urls[0], active:true})
					urls.shift()
				}
			});

			if(urls.length > 0)
			{
				await urls.forEach(singleURL=>{
					if(singleURL.indexOf("://") == -1)
					{
						singleURL = "https://" + singleURL //No I18N
					}

					BROWSER.tabs.create({url:singleURL, active:false})
				})
			}
		}
	}

	if(message.NewTabPageLocation !== undefined)
	{
		if(message.NewTabPageLocation.indexOf("://") === -1) //In client level as well, this should be handled
		{
			message.NewTabPageLocation = "https://"+message.NewTabPageLocation //No I18N	
		}

		BROWSER.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
			if(changeInfo.status === "complete" && isNewTab(tab))
			{
				BROWSER.tabs.update(tabId, {url:message.NewTabPageLocation, active:true})
			}
		});
	}
}

function isNewTab(tab){
	return (
        (tab.url !== undefined && (tab.url.includes("://newtab") || tab.url.includes("://new-tab-page"))) ||   //No I18N
        (tab.pendingUrl !== undefined && (tab.pendingUrl.includes("://newtab") || tab.pendingUrl.includes("://new-tab-page")))  //No I18N
    );
}

Port.prototype.postDOMContent = function(bodyContent, tabId, url, callback) {
	if (!this.checkPortState(callback)){
		return
	}
	this.port.postMessage({
		'id':this.registerCallback(callback), //No I18N
		'command':'invokeRouter', //No I18N
		'domcontent':bodyContent, //No I18N
		'tabId':tabId, //No I18N
		'url':url //No I18N
	});
}

Port.prototype.postOverRideDetails = function(overriddenDetails, callback){
	if(!this.checkPortState(callback)){
		return
	}
	this.port.postMessage({
		'id':this.registerCallback(callback), //No I18N
		'command':'categoryblockoverride', //No I18N
		'overriddendetails':overriddenDetails //No I18N
	})
}

Port.prototype.posttabWebHistoryUpdate = function(datatobepost,callback) {
	if (!this.checkPortState(callback)){
		return
	}
	this.port.postMessage({
		'id':this.registerCallback(callback), //No I18N
		'command':'addOrUpdateHistory', //No I18N
		'HistoryItem':datatobepost //No I18N
	});
}

Port.prototype.postWebHistoryRemove = function(tabId, callback) {
	if (!this.checkPortState(callback)){
		return
	}
	this.port.postMessage({
		'id':this.registerCallback(callback), //No I18N
		'command':'updateRemovedHistory', //No I18N
		'tabId':tabId, //No I18N
		"closedTime": Date.now() //No I18N
	});
}

Port.prototype.UploadHelper = function() {
	var uploadNeeded = (this.check_upload || Object.keys(this.ruleJSON).length > 0) && !(this.filePickerNotNeeded); /*special variable to off this listner*/
	if (uploadNeeded)
	{
		if((BROWSER.tabs.onUpdated.hasListener(this.tabUpdationListner) === false)){
			BROWSER.tabs.onUpdated.addListener(this.tabUpdationListner)
		}
		// Register shadowhook.js as a dynamic content script (document_start + MAIN world)
		BROWSER.scripting.registerContentScripts([{
			id: "bsp-shadowhook", //No I18N
			matches: ["<all_urls>"], //No I18N
			js: ["js/shadowhook.js"], //No I18N
			allFrames: true, 
			matchOriginAsFallback: true, //Inject into about:blank/srcdoc iframes too
			runAt: "document_start", //No I18N
			world: "MAIN" //No I18N
		}])
		.catch(function() { /* already registered */ });
	}
	else
	{
		if (BROWSER.tabs.onUpdated.hasListener(this.tabUpdationListner) == true){
			BROWSER.tabs.onUpdated.removeListener(this.tabUpdationListner);
		}
		// Unregister shadowhook.js when upload filtering is not needed
		BROWSER.scripting.unregisterContentScripts({ ids: ["bsp-shadowhook"] }) //No I18N
		.catch(function() { /* not registered */ });
	}
}

Port.prototype.tabUpdationListerCallback = function(tabId, changeInfo, tab)
{
	if (changeInfo.status === "complete")
	{
		//as of now firefox don't have Window.showOpenFilePicker & window.showOpenDirectoryPicker, Watch this & remove the if check if released
		if (BROWSERTYPE !== "FIREFOX")
		{
			BROWSER.scripting.executeScript(
				{
					target: { tabId: tabId, allFrames: true }, // Injects into all frames
					files : ["js/filepicker.js"], //No I18N
					world: "MAIN" //for MonkeyPatching  //No I18N
				}
			)
			.catch(err=>{
				//console.error("Error Occured ", err) //No I18N
			})
		}

		// Fallback: also inject shadowhook.js via executeScript into all frames.
		// registerContentScripts may miss about:blank/srcdoc iframes created before
		// matchOriginAsFallback takes effect. executeScript(allFrames) reaches ALL frames.
		BROWSER.scripting.executeScript(
			{
				target: { tabId: tabId, allFrames: true },
				files : ["js/shadowhook.js"], //No I18N
				world: "MAIN" //No I18N
			}
		)
		.catch(err=>{
			//console.error("shadowhook inject error ", err) //No I18N
		})
	}
}
