BrowserSettings = function() {
    this.port = null;
    this.chrome_settings = {};
    this.privacySet = {};
    this.conSet = {};
    
    this.initialize();
};

BrowserSettings.prototype.getSettings = function() {
	var chromeVersion = 0;
	if (navigator.userAgentData) {
		navigator.userAgentData.brands.forEach(function (arrayItem) {
			if(arrayItem.brand == 'Chromium'){ chromeVersion = arrayItem.version;}	//No I18N
		 });
		 if(chromeVersion == 0) { chromeVersion = navigator.userAgentData.brands[0].version}
	}
	else{
		var versionString = window.navigator.appVersion.indexOf("Chrome/");				//No I18N
		chromeVersion = window.navigator.appVersion.substring(versionString+7,versionString+10);
		if(chromeVersion[2] == '.')	{chromeVersion=chromeVersion.slice(0,2);}
	}
	chrome_settings.PrivacySettings = privacySet ;
        chrome.privacy.services.passwordSavingEnabled.get({}, function(details) {
		if (details.value){
			privacySet.ManagedPassword = 0 ;
		}
		else{
			privacySet.ManagedPassword = 1 ;
		}
	});
	chrome.privacy.services.alternateErrorPagesEnabled.get({}, function(details) {
		if (details.value){
			privacySet.AlternateErrorPagesEnabled = 0 ;
		}
		else{
			privacySet.AlternateErrorPagesEnabled = 1 ;
		}
	});

	if(chromeVersion > 69){
		chrome.privacy.services.autofillAddressEnabled.get({}, function(details) {
			if (details.value){
				privacySet.AutofillAddressEnabled = 0 ;
			}
			else{
				privacySet.AutofillAddressEnabled = 1 ;
			}
		});
		chrome.privacy.services.autofillCreditCardEnabled.get({}, function(details) {
			if (details.value){
				privacySet.AutofillCreditCardEnabled = 0 ;
			}
			else{
				privacySet.AutofillCreditCardEnabled = 1 ;
			}
		});
	}
	else{
		chrome.privacy.services.autofillEnabled.get({}, function(details) {
			if (details.value){
				privacySet.AutoFillEnabled = 0 ;
			}
			else{
				privacySet.AutoFillEnabled = 1 ;
			}
		});
	}
	chrome.privacy.services.passwordSavingEnabled.get({}, function(details) {
		if (details.value){
			privacySet.PasswordSavingEnabled = 0 ;
		}
		else{
			privacySet.PasswordSavingEnabled = 1 ;
		}
	});
	chrome.privacy.services.safeBrowsingEnabled.get({}, function(details) {
		if (details.value){
			privacySet.SafeBrowsingEnabled = 0 ;
		}
		else{
			privacySet.SafeBrowsingEnabled = 1 ;
		}
	});
	chrome.privacy.services.safeBrowsingExtendedReportingEnabled.get({}, function(details) {
		if (details.value){
			privacySet.SafeBrowsingExtendedReportingEnabled = 0 ;
		}
		else{
			privacySet.SafeBrowsingExtendedReportingEnabled = 1 ;
		}
	});
	chrome.privacy.services.searchSuggestEnabled.get({}, function(details) {
		if (details.value){
			privacySet.SearchSuggestEnabled = 0 ;
		}
		else{
			privacySet.SearchSuggestEnabled = 1 ;
		}
	});
	chrome.privacy.services.spellingServiceEnabled.get({}, function(details) {
		if (details.value){
			privacySet.SpellingServiceEnabled = 0 ;
		}
		else{
			privacySet.SpellingServiceEnabled = 1 ;
		}
	});
	chrome.privacy.services.translationServiceEnabled.get({}, function(details) {
		if (details.value){
			privacySet.TranslationServiceEnabled = 0 ;
		}
		else{
			privacySet.TranslationServiceEnabled = 1 ;
		}
	});
	chrome.privacy.websites.thirdPartyCookiesAllowed.get({}, function(cookie) {
		if (cookie.value){
			privacySet.ThirdPartyCookies = 0 ;
		}
		else{
			privacySet.ThirdPartyCookies = 1 ;
		}
	});
	chrome.privacy.websites.hyperlinkAuditingEnabled.get({}, function(cookie) {
		if (cookie.value){
			privacySet.HyperlinkAuditingEnabled = 0 ;
		}
		else{
			privacySet.HyperlinkAuditingEnabled = 1 ;
		}
	});
	chrome.privacy.websites.referrersEnabled.get({}, function(cookie) {
		if (cookie.value){
			privacySet.ReferrersEnabled = 0 ;
		}
		else{
			privacySet.ReferrersEnabled = 1 ;
		}
	});
    
    chrome_settings.ContentSettings = conSet ;
    var types = ['cookies', 'images', 'javascript', 'location',//No I18N
	'popups', 'notifications', 'microphone', 'camera',//No I18N
	'unsandboxedPlugins', 'automaticDownloads'];									//No I18N
	types.forEach(function(type) {
		chrome.contentSettings[type].get( {primaryUrl: "http://*"}, this.contentSettingsCallback.bind(this, type));
	}.bind(this));
}

BrowserSettings.prototype.contentSettingsCallback = function(type, content) {	//No I18N
    if(content.setting === "allow"){				//No I18N
        conSet[type] = 0 ;
    } else if(content.setting === "block"){			//No I18N
        conSet[type] = 1 ;
    } else if(content.setting === "ask"){				//No I18N
        conSet[type] = 2 ;
    }
    
    if (type == "automaticDownloads") { //No I18N
        this.port.postBrowserSettings(chrome_settings);
    }
}

BrowserSettings.prototype.BrowserSettingsListner = function() {
	chrome_settings = {};
	privacySet = {};
	conSet = {};
	this.getSettings();
}

BrowserSettings.prototype.initialize = function() {
    this.port = new Port();
	this.BrowserSettingsListner() //for the first time
	setInterval(()=>{
		this.BrowserSettingsListner()
	}, 60*60*1000) //for every hour
}
