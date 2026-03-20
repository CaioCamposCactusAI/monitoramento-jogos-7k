ContentPort = function() {
	this.contentPort = {};
	this.tabID = null;
	this.port = null;
	this.requestdata = {};
	this.initialize();
}

ContentPort.prototype.connectCallback = function(contentScriptPort){

	if(contentScriptPort.sender.tab){
		this.tabID = contentScriptPort.sender.tab.id;
		this.contentPort[this.tabID] = contentScriptPort;

        if (messageToTab[this.tabID]) {
            if (messageToTab[this.tabID].action !== undefined) {
				BROWSER.tabs.sendMessage(this.tabID, messageToTab);
            }
        }

		contentScriptPort.onDisconnect.addListener(this.disconnectContentScript.bind(this, this.tabID));
	}
}

ContentPort.prototype.contentFilterCallback = function(request, sender, sendResponse)	
{	
	//worst case handle. Need to define Request Type & handle all type of request accordingly
	if (request.actiontype === "UploadBlock") {
        if (sender.tab && sender.tab.id) {
			this.requestdata = request;
            this.sendMessage(sender.tab.id);
        } 
		// else {
        //     console.error("No tab information available."); //No I18N
        // }
        // Send a response back if needed
        sendResponse({ success: true });
    }
	else{
		if(request.Request != undefined && request.Request == "UploadCheck")	//No I18N
		{
			sendResponse({
				"s": this.port.check_upload,	//No I18N
				"rule_json" : this.port.ruleJSON	//No I18N
			});
		}
		else if(request.Request != undefined && request.Request == "overridepage"){
			this.port.postOverRideDetails(request.overriddenDetails, null)
			overRidedPageDetails[request.overriddenDetails.tabId] = request.overriddenDetails
			BROWSER.tabs.update(request.overriddenDetails.tabId, {url: request.overriddenDetails.url});
		}
		else if(request.Request != undefined && request.Request == "FFAgreeStatus")
		{
			//console.log("Handled in ConsentHandler by Firefox Background JS");
			return;
		}
		else{
			this.port.postUploadData(request, sender.tab.id, sender.url, null);
		}
	}
}

ContentPort.prototype.disconnectContentScript = function(id){
	delete this.contentPort[id];
}

ContentPort.prototype.initialize = function(){
	this.port = new Port();
	BROWSER.runtime.onConnect.addListener(this.connectCallback.bind(this));
	BROWSER.runtime.onMessage.addListener(this.contentFilterCallback.bind(this));
}

ContentPort.prototype.sendMessage = function(id){
	var message = this.requestdata;
	message.actiontype = "Upload"; //No I18N

	BROWSER.tabs.query({active: true, currentWindow: true}, function(tabs) {
		BROWSER.tabs.sendMessage(id, {action:"cancelUpload",message:message});	//No I18N
	});
}
