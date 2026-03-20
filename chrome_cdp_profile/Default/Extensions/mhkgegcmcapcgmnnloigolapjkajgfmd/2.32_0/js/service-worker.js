//cross-platform check using chrome.runtime API
const browserIdentifier = chrome.runtime.getURL("manifest.json") //No I18N
const chromeIndex = browserIdentifier.indexOf("chrome-extension://")
const mozIndex = browserIdentifier.indexOf("moz-extension://")
const extensionId = chrome.runtime.id;

var BROWSER = ""
var BROWSERTYPE = ""
var isBrowserStartup = false

if(chromeIndex != -1)
{
	BROWSER = chrome
}
else if(mozIndex != -1)
{
	BROWSER = browser
}
if (extensionId === "bdgkacbeblomgnaoildjnppjkamgoogc") {
    BROWSERTYPE = "EDGE";	//No I18N
}

var overRidedPageDetails = {}
var webHistory = {};
self.importScripts('nativePort.js', 'browserSettings.js', 'filenamedetector.js','downloadManager.js', 'contentPort.js', 'historyCollector.js', 'webMetering.js', 'routingLogic.js');//No I18N
registerListeners();
function registerListeners () {
	var browserRouter = new ExtensionLogic();
	var downloadManager = new DownloadManager();
	var historyCollector = new HistoryCollector();
	var webMetering = new WebMetering();
    var contentPort = new ContentPort();
	var browserSettings = new BrowserSettings();
}

//startup event lisetening
chrome.runtime.onStartup.addListener(function(details){
	isBrowserStartup = true;
})





