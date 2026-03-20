//content script doesn't comes under extension, so need to duplicate this code

//cross-platform check using chrome.runtime API
const browserIdentifier = chrome.runtime.getURL("manifest.json") //No I18N
const chromeIndex = browserIdentifier.indexOf("chrome-extension://")
const mozIndex = browserIdentifier.indexOf("moz-extension://")

var BROWSER = ""
if (chromeIndex != -1) {
    BROWSER = chrome
}
else if (mozIndex != -1) {
    BROWSER = browser
}

ContentScript = function () {
    this.connectToExtension();
    this.port = null;
};


ContentScript.prototype.connectToExtension = function () {
    this.port = BROWSER.runtime.connect({ name: "bsp-contentScript" });   //No I18N
    BROWSER.runtime.onMessage.addListener(this.onMessageReceived.bind(this));
};

ContentScript.prototype.onMessageReceived = function (message, sendResponse) {
    if ((message.action === "cancelDownload" || message.action === "cancelUpload") && !document.getElementById("BSP-download-restriction-modal")) {
        showDownloadRestrictionModal(message);
    }
    if (window.location.href.indexOf("url_restriction.html") != -1) {
        BROWSER.tabs.getCurrent(function (currentTab) {

            var category = ""
            if(message[currentTab.id].BlockedCategory !== undefined) {
                category = message[currentTab.id].BlockedCategory
            }

            if (message[currentTab.id].custom_message !== undefined && verifySanity(message[currentTab.id].custom_message)) {
                var curTabMsg = message[currentTab.id].custom_message;

                //domain replacement
                if (message[currentTab.id].domain !== undefined) {
                    curTabMsg = curTabMsg.replace("[domain]", message[currentTab.id].domain)
                }

                //category replacement
                curTabMsg = curTabMsg.replace("[category]", category)

                var supportingTags = []

                //href add for help link
                const pattern = /\[(.*?)\]\((.*?)\)/g;

                if (curTabMsg.match(pattern)) {
                    supportingTags.push('a')
                }
                curTabMsg = curTabMsg.replace(pattern, '<a href="$2">$1</a>');

                document.getElementById("blockMessage").innerHTML = curTabMsg;
            }
            else
            {
                var def_message
                if(!message[currentTab.id].ShowOverrideUI)
                {
                    if(category !== "")
                    {
                        def_message = `Access to <b>${message[currentTab.id].domain}</b> (<b>Category: ${category}</b>) is restricted by your organization. For further assistance, please reach out to your system administrator.`;
                    }
                    else
                    {
                        def_message = `The website <b>${message[currentTab.id].domain}</b> is currently blocked by your organization. Please contact your system administrator for further details.`;
                    }
                }
                else
                {
                    def_message = `Your organization has restricted access to <b>${message[currentTab.id].domain}</b> due to its classification under (<b>Category: ${category}</b>). If you believe this restriction is incorrect, you may use the override option. Your administrator will be notified of this action.`;
                }

                document.getElementById("blockMessage").innerHTML = def_message;
            }

            if (message[currentTab.id].custom_logo !== undefined) {
                document.getElementById("bspimage").src = message[currentTab.id].custom_logo;
            }
            if (message[currentTab.id].custom_mail_id !== undefined) {
                document.getElementById("mailId").textContent = message[currentTab.id].custom_mail_id;
            }
            else {
                var maildiv = document.getElementById("mailbox");
                maildiv.remove();
            }

            if (message[currentTab.id].ShowOverrideUI === true) {
                var accessReq = document.getElementById("accessReq");
                accessReq.style.display = "inline-flex"

                //show Request box on click
                accessReq.addEventListener("click", function () {
                    accessReq.style.display = "none";

                    var reqForm = document.getElementById("reqForm");
                    if (reqForm) {
                        reqForm.style.display = "inline-flex";
                    }

                    var reqFormBtn = document.getElementById("reqFormBtn");
                    if (reqFormBtn) {
                        reqFormBtn.style.display = "inline-flex";

                        //page open code handle
                        var reason = document.getElementById("reason")
                        var reasonInput
                        var isValidRegex = true

                        reason.addEventListener("input", function(e){
                            reasonInput = reason.value
                            const regex = /^[a-zA-Z0-9\s+?!,()@%.\-:_*\\.=\[\]]+$/;

                            if((!regex.test(reasonInput) && reasonInput !== "") || reasonInput.length >= 250)
                            {
                                reason.style.border = "2px solid red"
                                isValidRegex = false
                            }
                            else
                            {
                                reason.style.border=""
                                isValidRegex = true
                            }
                        })

                        reqFormBtn.addEventListener("click", function (e) {
                            if(isValidRegex)
                            {
                                if (reason.value) {
                                    message[currentTab.id].override_reason = reason.value
                                }
                                BROWSER.runtime.sendMessage({ "Request": "overridepage", overriddenDetails: message[currentTab.id] }) //No I18N
                            }
                        })
                    }
                });

            }
        });
    }
}

function showDownloadRestrictionModal(incomingMessage) {
    var extensionPath = BROWSER.runtime.getURL(""); //No I18N
    
    fetch(extensionPath + "download_restriction.html") //No I18N
        .then(response => response.text())
        .then(html => {
            // Find your modal container and set its innerHTML
            let modal = document.getElementById("BSP-download-restriction-modal");
            if (!modal) {
                // If modal doesn't exist, create and append it
                modal = document.createElement("div");
                modal.id = "BSP-download-restriction-modal";
                modal.style.position = "fixed";
                modal.style.top = "0";
                modal.style.left = "0";
                modal.style.width = "100vw";
                modal.style.height = "100vh";
                modal.style.background = "rgba(0,0,0,0.5)";//No I18N
                modal.style.zIndex = "99999";
                modal.style.display = "flex";
                modal.style.justifyContent = "center";//No I18N
                modal.style.alignItems = "center";//No I18N
            }
            modal.innerHTML = html;
            var messageContainer = modal.querySelector(".bspblockmessage");//No I18N

            var message = incomingMessage.message

            let blockheader = modal.querySelector(".bspblockheader"); //No I18N
            if (blockheader && message.actiontype === "Upload") {
                blockheader.textContent = "Upload Not Allowed"; //No I18N
            }
            if (blockheader && message.actiontype === "Download") {
                blockheader.textContent = "Download Not Allowed"; //No I18N
            }
            //custom Message Population
            if (messageContainer) {
                //custom message

                if (message.custom_message !== undefined && verifySanity(message.custom_message)) {
                   
                    if (message.custom_message.includes("[domain]")) {
                        if (message.domain !== undefined) {
                            message.custom_message = message.custom_message.replace("[domain]", "<b class='bsp-b'>" + message.domain + "</b>");
                        } else {
                            message.custom_message = message.custom_message.replace("[domain]", "");
                        }
                    }

                    if (message.custom_message.includes("[filetype]")) {
                        if (message.filetype !== undefined) {
                            message.custom_message = message.custom_message.replace("[filetype]", "<b class='bsp-b'>" + message.filetype + "</b>");
                        }
                        else {
                            message.custom_message = message.custom_message.replace("[filetype]", "");
                        }
                    }

                    if (message.custom_message.includes("[filesize]")) {
                        if (message.filesize !== undefined) {
                            message.custom_message = message.custom_message.replace("[filesize]", "<b class='bsp-b'>" + message.filesize + "</b>");
                        }
                        else {
                            message.custom_message = message.custom_message.replace("[filesize]", "");
                        }
                    }

                    if (message.custom_message.match(/\[.*?\]\(.*?\)/g)) {
                        message.custom_message = message.custom_message.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank">$1</a>');
                    }
                    messageContainer.innerHTML = message.custom_message;
                }
                else {
                    let details =
                        (message.domain ? ` from <b class="bsp-b">${message.domain}</b>` : "") +
                        (message.filetype ? ` of type <b class="bsp-b">${message.filetype}</b>` : "") +
                        (message.filesize ?
                            ((message.domain || message.filetype) ? ` and of size <b class="bsp-b">${message.filesize}</b>` : ` of size <b class="bsp-b">${message.filesize}</b>`)
                            : "");
                    let msg = `The ${message.actiontype} attempted${details} has been blocked by your administrator.`;
                    messageContainer.innerHTML = msg;
                }

                //custom mail id
                if (message.custom_mail_id !== undefined) {
                    var mailId = message.custom_mail_id;

                    var mailContainer = modal.querySelector(".bsp-admin-contact");//No I18N
                    var mailIDParagraph = modal.querySelector(".bsp-admin-contact-p");//No I18N

                    if (mailIDParagraph && mailContainer) {
                        mailIDParagraph.style.display = "inline";
                        mailContainer.innerHTML = `<a href="mailto:${mailId}">${mailId}</a>`;
                    }
                }

                //custom logo
                if (message.custom_logo !== undefined) {
                    var logo = message.custom_logo;
                    var logoImage = modal.querySelector(".bsp-cus-logo");//No I18N

                    if (logoImage) {
                        logoImage.src = logo;
                    }
                }
            }


            document.body.appendChild(modal);

            //add event listener to close the modal
            var closeButton = modal.querySelector(".bsp-closeBtn");//No I18N
            if (closeButton) {
                closeButton.addEventListener("click", function () {
                    modal.style.display = "none";
                    modal.remove();
                });
            }
        });
}

function verifySanity(message) {
    if (!message || typeof message !== "string") {
        return false;
    }

    // Your whitelist regex
    const regex = /^([a-zA-Z0-9\s\+?!,;%()@.\-:_*\./\\=\[\]\{\#\}$`~\^]|[^\u0020-\u007F])+$/;
    return regex.test(message);
}


contentScript = new ContentScript();
