
var urlContentDisposition = {}

//as of now this is not in use
const kPrimaryMappings = [
    // Must precede audio/webm .
    { mimeType: "video/webm", extensions: "webm" },//NO I18N

    // Must precede audio/mp3
    { mimeType: "audio/mpeg", extensions: "mp3" },//NO I18N

    { mimeType: "application/wasm", extensions: "wasm" },//NO I18N
    { mimeType: "application/x-chrome-extension", extensions: "crx" },//NO I18N
    { mimeType: "application/xhtml+xml", extensions: "xhtml,xht,xhtm" },//NO I18N
    { mimeType: "audio/flac", extensions: "flac" },//NO I18N
    { mimeType: "audio/mp3", extensions: "mp3" },//NO I18N
    { mimeType: "audio/ogg", extensions: "ogg,oga,opus" },//NO I18N
    { mimeType: "audio/wav", extensions: "wav" },//NO I18N
    { mimeType: "audio/webm", extensions: "webm" },//NO I18N
    { mimeType: "audio/x-m4a", extensions: "m4a" },//NO I18N
    { mimeType: "image/avif", extensions: "avif" },//NO I18N
    { mimeType: "image/gif", extensions: "gif" },//NO I18N
    { mimeType: "image/jpeg", extensions: "jpeg,jpg" },//NO I18N
    { mimeType: "image/png", extensions: "png" },//NO I18N
    { mimeType: "image/apng", extensions: "png,apng" },//NO I18N
    { mimeType: "image/svg+xml", extensions: "svg,svgz" },//NO I18N
    { mimeType: "image/webp", extensions: "webp" },//NO I18N
    { mimeType: "multipart/related", extensions: "mht,mhtml" },//NO I18N
    { mimeType: "text/css", extensions: "css" },//NO I18N
    { mimeType: "text/html", extensions: "html,htm,shtml,shtm" },//NO I18N
    { mimeType: "text/javascript", extensions: "js,mjs" },//NO I18N
    { mimeType: "text/xml", extensions: "xml" },//NO I18N
    { mimeType: "video/mp4", extensions: "mp4,m4v" },//NO I18N
    { mimeType: "video/ogg", extensions: "ogv,ogm" },//NO I18N

    // This is a primary mapping (overrides the platform) rather than secondary
    // to work around an issue when Excel is installed on Windows. Excel
    // registers csv as application/vnd.ms-excel instead of text/csv from RFC
    // 4180. See https://crbug.com/139105.
    { mimeType: "text/csv", extensions: "csv" }//NO I18N
];

//this headers is needed always that even after download filter is removed, and applied the data should be collected
BROWSER.webRequest.onHeadersReceived.addListener(
	function(details) {
		var singleUrlInfo = {}
		for (let i = 0; i < details.responseHeaders.length; i++) {
			var curresponseHeader = details.responseHeaders[i].name.toLowerCase()
			if(curresponseHeader.indexOf("disposition") != -1)
			{
				singleUrlInfo["content-disposition"] = details.responseHeaders[i].value
			}
			if(curresponseHeader.indexOf("content-type") != -1)
			{
				singleUrlInfo["content-type"] = details.responseHeaders[i].value
			}
		}
		urlContentDisposition[details.url] = singleUrlInfo
	},
	{ urls: ["<all_urls>"] },//NO I18N
	["responseHeaders"]
);

//referred from chromium source code
function doExtractFileName(spec) 
{
	let queryIndex = spec.indexOf('?');
	if (queryIndex !== -1) {
		spec = spec.slice(0, queryIndex);
	}

	let fileEnd = spec.length;
	for (let i = spec.length - 1; i >= 0; i--) 
	{
		if (spec[i] === ';') 
		{
			fileEnd = i;
		} else if (isSlashOrBackslash(spec[i])) {
			return spec.slice(i + 1, fileEnd);
		}
	}

	return spec.slice(0, fileEnd);
}

function isSlashOrBackslash(char) 
{
	return char === '/' || char === '\\';
}

//[1] - Resolved From Content-disposition Header
//[2] - From data:image/
//[3] - From URL

function getFilterFileName(id) {
    return new Promise((resolve, reject) => {
        chrome.downloads.search({ id: id }, function (downloadArray) {
            if (chrome.runtime.lastError) {
                return reject(chrome.runtime.lastError);
            }

            var data = downloadArray[0];
            var filename = "";
            var currentContentDisposition;

            // Extracting content-disposition from either the URL or referrer
            if (urlContentDisposition.hasOwnProperty(data.url) && urlContentDisposition[data.url].hasOwnProperty("content-disposition")) {
                currentContentDisposition = urlContentDisposition[data.url]["content-disposition"];
            } else if (urlContentDisposition.hasOwnProperty(data.referrer) && urlContentDisposition[data.referrer].hasOwnProperty("content-disposition")) {
                currentContentDisposition = urlContentDisposition[data.referrer]["content-disposition"];
            }
            // Extracting filename from content-disposition if available
            if (currentContentDisposition) {
                var match = currentContentDisposition.match(/filename\*?=((['"])[\s\S]*?\2|[^;\n]*)/);
                if (match && match[1]) {
                    filename = match[1].replace(/(^")|("$)/g, ''); // Remove surrounding quotes
                }
            }

            // Handle data URLs for images
            if (!filename && data.url.startsWith("data:image/")) {
                var extension = data.url.split(';')[0].split('/')[1];
                extension = extension === "jpeg" ? "jpg" : extension;//NO I18N
                filename = "untitled." + extension;//NO I18N
            }

            // Fallback: Extract filename from the URL
            if (!filename && !data.url.startsWith("blob:") && !data.url.startsWith("about:")) {
                filename = doExtractFileName(data.finalUrl) || doExtractFileName(data.url) || doExtractFileName(data.referrer);
                if (!(data.filename.endsWith(".htm") || data.filename.endsWith(".html"))) {
                    var contenttype;
                    if (urlContentDisposition.hasOwnProperty(data.url) && urlContentDisposition[data.url].hasOwnProperty("content-type")) {
                        contenttype = urlContentDisposition[data.url]["content-type"];
                    } else if (urlContentDisposition.hasOwnProperty(data.referrer) && urlContentDisposition[data.referrer].hasOwnProperty("content-type")) {
                        contenttype = urlContentDisposition[data.referrer]["content-type"];
                    }
                    if (contenttype && contenttype.startsWith("image/")) {
                        var newExtension = contenttype.split("/")[1];
                        newExtension = newExtension === "svg+xml" ? "svg" : newExtension;//NO I18N
                        if (newExtension !== "jpg" && newExtension !== "jpeg") {
                            let dotIndex = filename.lastIndexOf(".");
                            filename = filename.substring(0, dotIndex) + "." + newExtension;
                        }
                    }
                } else {
                    filename = ""; // Save as triggered, so ignore filter filename
                }
            }

            if(filename.indexOf(".") == -1)
            {
                filename = ""
            }

            resolve(filename);
        });
    });
}
