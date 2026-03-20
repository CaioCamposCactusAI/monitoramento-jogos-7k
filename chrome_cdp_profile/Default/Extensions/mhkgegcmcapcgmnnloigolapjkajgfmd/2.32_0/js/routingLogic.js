var messageToTab = {};
var WebRequestCaptured = {};
var requestId = [];
var loadingTabIds = [];
const unallowedRegex = /[^\p{L}\p{M}\p{N}\p{Z}\p{Cf}\p{Cs}\s.,!':_\\—\-]/gu;
ExtensionLogic = function() {

	this.port = null;
	this.routerReadyFlag = false;
	this.redirectURLDetails = {};
	this.redirect_listener = this.redirectFilter.bind(this);
	this.request_listener = this.requestFilter.bind(this);
	this.tabUpdationListner = this.tabUpdationListerCallback.bind(this);
	this.resourceID = null;
	this.isNativeHostReady = false;
	
	this.initialize();
};

ExtensionLogic.prototype.portConnected = function(message) {
	console.log("Port connected");
	this.routerReadyFlag =  true;
	if(BROWSER == chrome)
	{
		BROWSER.management.getAll(this.extensionGetAll.bind(this));
	}
	this.postLoadedTabs();
};

ExtensionLogic.prototype.portDisconnected = function() {
	console.error('Native port not reachable because native host exited!'); //No I18N
};

ExtensionLogic.prototype.postLoadedTabs = async function () {
	let queryOptions = {};
	let Objquery = await BROWSER.tabs.query(queryOptions)
	for (let c = 0; c < Objquery.length; c++) {
		var url = Objquery[c].url;
		if(url == undefined){
			if(Objquery[c].pendingUrl != undefined){
				url = Objquery[c].pendingUrl;
			}
			else{
				continue
			}
		}
	
		if (url == undefined || (!url.trim().startsWith('http:') && !url.trim().startsWith('https:') && !url.trim().startsWith('file:'))) {
			console.log("preloaded URL is not a valid");	//No I18N
			continue;
		}
		this.port.invokeRouter(url, Objquery[c].id, this.responseMessageHandler.bind(this));
	}
	console.log("Loaded Tabs posting completed")	//No I18N
}

ExtensionLogic.prototype.requestFilter = function(details) {
	if(!isNewRequest(details))
	{
		return;
	}

	var url = details.url
	WebRequestCaptured[details.tabId] = {
		'url':url, //No I18N
		'invokeRouterSend':true //No I18N
	};
	if (!url.trim().startsWith('http:') && !url.trim().startsWith('https:') && !url.trim().startsWith('file:')) {
		return;
	}
	if(this.routerReadyFlag){
		var redirectedURLTabDetails = this.redirectURLDetails[details.url];
		if(redirectedURLTabDetails === undefined){
			this.port.invokeRouter(details.url,details.tabId,this.responseMessageHandler.bind(this));
		}
		else{
			if(redirectedURLTabDetails.tabId === details.tabId) { 
				this.port.redirectedRequestRouter(details.url,details.tabId,redirectedURLTabDetails.oldUrl,this.responseMessageHandler.bind(this));
			}
		}
	}
	else { 
		console.log("Native messaging host still not initialized");
	}
};

function isNewRequest(details)
{
	//prerender  in document
	if(details.documentLifecycle === 'prerender' || requestId.includes(details.requestId))
	{
		return false;
	}

	//header value has prefetch || serviceworker Navigation preload
	if(details.requestHeaders !== undefined)
	{
		for(let i=0; i<details.requestHeaders.length; i++)
		{
			if(((details.requestHeaders[i].name.includes("Purpose") || (details.requestHeaders[i].name === "X-moz")) && details.requestHeaders[i].value.includes("prefetch")) ||
			   (details.requestHeaders[i].name.includes("Service-Worker-Navigation-Preload") && details.requestHeaders[i].value === "true"))
			{
				return false;
			}
		}
	}

	//overridden page
	if(details.tabId in overRidedPageDetails && details.url.indexOf(overRidedPageDetails[details.tabId].url) != -1)
	{
		delete overRidedPageDetails[details.tabId]
		WebRequestCaptured[details.tabId] = {
			'url':details.url, //No I18N
			'invokeRouterSend':true //No I18N
		};
		return false
	}

	if(details.requestId !== undefined)
	{
		requestId.push(details.requestId);
	}
	
	return true;
}

ExtensionLogic.prototype.redirectFilter = function(details) {
	var url = details.url;
	WebRequestCaptured[details.tabId] = details.url;
	if (!url.trim().startsWith('http:') && !url.trim().startsWith('https:') && !url.trim().startsWith('file:')) {
		return;
	}
	if(this.routerReadyFlag){
		this.redirectURLDetails[details.redirectUrl] = { oldUrl : details.url,tabId : details.tabId } ;
	}
	else {
		console.log("Native messaging host still not initialized");
	}
};

ExtensionLogic.prototype.responseMessageHandler = function(message) {
	if(message.action === "closeTab") {
		BROWSER.management.getSelf(function(myExtension){
			BROWSER.tabs.query({active: true, currentWindow: true}, function(tabs) {
				if(message.custom_url){
					BROWSER.tabs.update(message.tabId, {url: message.custom_url, active :true});
				}
				else{
					BROWSER.tabs.update(message.tabId,{url:"/url_restriction.html", active:true}) //No I18N
					messageToTab[message.tabId] = message;
				}
        	});
		});
	}
	if(message.action === "removeTab") {
		BROWSER.tabs.remove(message.tabId,function(){
			console.log("Tab closed");
		});
	}
	if(this.isNativeHostReady === false) {
		if(message.action !== "nativeHostNotInitialized") {
			this.isNativeHostReady = true;
		}
	}
	if(message.URLToDeleteObject !== undefined){
		delete this.redirectURLDetails[message.URLToDeleteObject];
	}
	if(message.action === "scrappageandignore"){
		BROWSER.tabs.get(message.tabId, (tab)=>{
			if(tab.status === "complete")
			{
				if(tab.url !== undefined)
				{
					if(message.url === tab.url) 
					{
						this.injectScript(message.tabId)
					}
				}
			}
			else
			{
				loadingTabIds.push(message.tabId)
			}
		})
	}
	if (WebRequestCaptured.hasOwnProperty(message.tabId)) {
		delete WebRequestCaptured[message.tabId];
	}
};

ExtensionLogic.prototype.updateExtensionInventory = function(Status,ExtensionInfo) {
		var necessaryInfo = {};
		if( typeof(ExtensionInfo) === "object" ) {
			necessaryInfo.ExtensionName = RemoveUnallowedChars(ExtensionInfo.name);
			necessaryInfo.Description = RemoveUnallowedChars(ExtensionInfo.description);
			necessaryInfo.Version = ExtensionInfo.version;
			necessaryInfo.State = ExtensionInfo.enabled;
			necessaryInfo.VersionName = ExtensionInfo.versionName;
			necessaryInfo.Id = ExtensionInfo.id;
			necessaryInfo.ShortName = RemoveUnallowedChars(ExtensionInfo.shortName);
			necessaryInfo.MayDisableByUser = ExtensionInfo.mayDisable;
			necessaryInfo.Type = ExtensionInfo.type;
			necessaryInfo.OfflineEnabled = ExtensionInfo.offlineEnabled;
			necessaryInfo.HomepageUrl = ExtensionInfo.homepageUrl;
			necessaryInfo.UpdateUrl = ExtensionInfo.updateUrl;
			necessaryInfo.HostPermissions = ExtensionInfo.hostPermissions;
			necessaryInfo.Permissions = ExtensionInfo.permissions;
			necessaryInfo.DisabledReason = ExtensionInfo.disabledReason;
			necessaryInfo.ExtensionInstallType = ExtensionInfo.installType;

			if( typeof(ExtensionInfo.mayEnable) !== undefined ) { 
				if(ExtensionInfo.mayEnable === false) {
					necessaryInfo.disabledReason = "disabled_due_to_policy";  //No I18N
				}
			}
		}
		else if( typeof(ExtensionInfo) === "string" ) {
			necessaryInfo.Id = ExtensionInfo;
		}
		necessaryInfo.eventType = Status;
		this.port.updateExtensionInventory(necessaryInfo,null);
};

ExtensionLogic.prototype.extensionGetAll = function(result) {
	var extension_info_array = new Array();
	for (var i = 0; i < result.length; i++) { 
		var extDetails = {};
		extDetails.ExtensionName = RemoveUnallowedChars(result[i].name);
		extDetails.Description = RemoveUnallowedChars(result[i].description);
		extDetails.Version = result[i].version;
		extDetails.State = result[i].enabled;
		extDetails.VersionName = result[i].versionName;
		extDetails.Id = result[i].id;
		extDetails.ShortName = RemoveUnallowedChars(result[i].shortName);
		extDetails.MayDisableByUser = result[i].mayDisable;
		extDetails.Type = result[i].type;
		extDetails.OfflineEnabled = result[i].offlineEnabled;
		extDetails.HomepageUrl = result[i].homepageUrl;
		extDetails.UpdateUrl = result[i].updateUrl;
		extDetails.HostPermissions = result[i].hostPermissions;
		extDetails.Permissions = result[i].permissions;
		extDetails.DisabledReason = result[i].disabledReason;
		extDetails.ExtensionInstallType = result[i].installType;

		if( typeof(result[i].mayEnable) !== undefined ) { 
			if(result[i].mayEnable === false) {
				extDetails.disabledReason = "disabled_due_to_policy";  //No I18N
			}
		}
		extension_info_array.push(extDetails);
	}
	this.port.postInstallExtensionInventory(extension_info_array,null);
};

ExtensionLogic.prototype.initialize = function() {
	BROWSER.webRequest.onSendHeaders.addListener(
		this.request_listener,
        {urls: ['http://*/*', 'https://*/*'], types: ['main_frame']}, //NO I18N
		["requestHeaders"]  //No I18N
    );
	
	BROWSER.webRequest.onBeforeRedirect.addListener((details)=>{
		this.redirect_listener;
		},
		{urls: ['http://*/*', 'https://*/*'], types: ['main_frame']}	//No I18N
		);
	
	//just for handle the page loads from the service worker
	BROWSER.tabs.onUpdated.addListener(this.tabUpdationListner)

	if(BROWSER == chrome)
	{
		BROWSER.management.onInstalled.addListener(this.updateExtensionInventory.bind(this,"Install"));
		BROWSER.management.onEnabled.addListener(this.updateExtensionInventory.bind(this,"Enable"));
		BROWSER.management.onDisabled.addListener(this.updateExtensionInventory.bind(this,"Disable"));
		BROWSER.management.onUninstalled.addListener(this.updateExtensionInventory.bind(this,"Uninstall"));	
	}
	
	this.port = new Port(this.portConnected.bind(this), this.portDisconnected.bind(this), 1, this.WebRequestListener.bind(this));

};

ExtensionLogic.prototype.WebRequestListener = function(flag)
{
	if(flag == true) {
		if (BROWSER.webRequest.onSendHeaders.hasListener(this.request_listener) == false) {
			BROWSER.webRequest.onSendHeaders.addListener(
				this.request_listener,
				{urls: ['http://*/*', 'https://*/*'], types: ['main_frame']}, //No I18N
				["requestHeaders"] //No I18N
			);
		}
		if((BROWSER.tabs.onUpdated.hasListener(this.tabUpdationListner) === false)){
			BROWSER.tabs.onUpdated.addListener(tabUpdationListner)
			
		}
		
	}
	else{
		if (BROWSER.webRequest.onSendHeaders.hasListener(this.request_listener) == true) {
			BROWSER.webRequest.onSendHeaders.removeListener(this.request_listener);
		}
		if (BROWSER.tabs.onUpdated.hasListener(this.request_listener) == true){
			BROWSER.tabs.onUpdated.removeListener(this.request_listener);
		}
	}

};

ExtensionLogic.prototype.tabUpdationListerCallback = function(tabId, changeInfo, tab)
{
	
	setTimeout(() => { 
		if (tab.url != undefined && tabId != undefined) {
			if (changeInfo.url || BROWSERTYPE === "EDGE") {
				if (WebRequestCaptured[tabId] == undefined || 
				   !(WebRequestCaptured[tabId].url == tab.url && WebRequestCaptured[tabId].invokeRouterSend)) {
					this.request_listener({ tabId: tabId, url: tab.url });
					delete WebRequestCaptured[tabId];
				}	
			}
			if(changeInfo.status){
				if(changeInfo.status === "complete" && loadingTabIds.includes(tabId)){
					loadingTabIds = loadingTabIds.filter(Id => Id != tabId)
					setTimeout(()=>{
						this.injectScript(tabId)
					}, 2000) //Bing takes time to load
				}
			}
		}
	}, 500);	
}

ExtensionLogic.prototype.injectScript = function(tabId)
{
	BROWSER.scripting.executeScript({
		target: { tabId: tabId }, // Injects into all frames
		files : ["js/data-extractor.js"] //No I18N
	})
	.then(injectionResults => {
		for (const { _, result } of injectionResults) {
			var domContent = result.title+"\n"+result.metaDescription+"\n"+result.text //No I18N
			this.port.postDOMContent(domContent, tabId, result.url, this.responseMessageHandler.bind(this))
		}
	})
	.catch(err=>{
		console.error("Error Occured ", err) //No I18N
	})
}

//Remove UnAllowed Characters from String
function RemoveUnallowedChars(inputString)
{
	return RegexReplace(inputString, unallowedRegex, "");
}

//Generic Regex Replace function
function RegexReplace(inputString, regexPattern, replaceChar)
{
	return inputString.replace(regexPattern, replaceChar);
}