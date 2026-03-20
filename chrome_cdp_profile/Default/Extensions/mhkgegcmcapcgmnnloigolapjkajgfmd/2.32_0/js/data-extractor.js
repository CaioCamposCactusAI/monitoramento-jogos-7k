/**
 * Implementation of website data extracting script
 * 
 * @author Sivarajakani M
 */

/**
 * @description
 * This function removes some tags and extracts innerText from specific tags
 * 
 * @returns {
 * 	{
 *		text: string;
 *		title: string;
 *		meta_keywords: string;
 *		meta_description: string;
 *		lang: string;
 *		status: 'success';
 *		message: string;
 *		extraction_time: number
 * } |
 * 	{ status: 'failure', message: string, page_source: string }
 * }
 */
function getData() {

    const START_TIME = performance.now();

    // Define regex patterns
    const NON_WHITESPACE_END = /\S$/;
    const NON_WHITESPACE_START = /^\S/;
    const JUST_WHITESPACE = /^\s+$/;
    const WHITESPACE = /\s*(\n)\s*|\s+/g;

    // Reference: https://unicode-explorer.com/b/2000
    const INVISIBLE_CHARACTERS = /[\u200B-\u200F\u2028-\u202F\u205F-\u206F\uFEFF]+/g;

    // Get document as string
    const documentString = document.documentElement.outerHTML;
    let documentObject;

    try {
        // Try to parse the string document
        documentObject = new window.DOMParser().parseFromString(documentString, 'text/html');  // No I18N
    } catch (error) {

        // Return the error
        return {
            'status': 'failure',  // No I18N
            'message': error ? error.message || String(error): 'Something went wrong, while parsing the document',  // No I18N
            'page_source': documentString  // No I18N
        };
    }

    // Create text area to sanitize text using textNode
    const textArea = documentObject.createElement('textarea');

    // Define excludeTags and its default values
    const excludeTags = ['head', 'noscript', 'script', 'style'];  // No I18N

    function removeTagsByName(parentNode, tagName) {
        // Get tags from parentNode
        const tags = parentNode.querySelectorAll(tagName);
        const tagsLength = tags.length;

        // Remove child from parent until tags have elements
        for (let i = 0; i < tagsLength; i++) tags[i].parentNode?.removeChild(tags[i]);
    }

    function sanitize(text) {
        // NOTE: Playwright itself has parameter to bypass CSP

        // Create new text node to sanitize the text
        //  NOTE: TextNode doesn't have innerText attribute to get text
        const textNode = documentObject.createTextNode(text);
        // Actually it doesn't removes XSS attack, just put escape characters to prevent execution

        // Clear textArea 
        textArea.innerHTML = '';

        // Append textNode in <textarea> tag
        textArea.appendChild(textNode);

        // Get text from <textarea> tag
        return textArea.textContent || '';
    }

    // Strip whitespace
    function stripWhitespace(text) {
        if (JUST_WHITESPACE.test(text)) return '';

        return text.replace(WHITESPACE, (_, newlineCharacter) => newlineCharacter || ' ');
    }

    // Strip invisible characters
    function stripInvisibleChars(text) {
        return text.replace(INVISIBLE_CHARACTERS, '')
    }

    function removeTags(doc) {
        const excludeTagsLength = excludeTags.length;

        for (let i = 0; i < excludeTagsLength; i++) removeTagsByName(doc, excludeTags[i]);
    }

    function getTextFromNode(node) {
        const nodeLength = node.childNodes.length;

        // Define local variables
        let i, child, nodeType, text, result = '';
        let previousNodeType = -1;

        // Iterate all childNodes
        for (i = 0; i < nodeLength; i++) {
            // Get a childNode from the node
            child = node.childNodes[i];
            nodeType = child.nodeType;

            text = undefined;

            // Recursive call, if the child is Node.ELEMENT_NODE = 1
            if (nodeType === 1) {

                // <img> does not have any children, so no need iteration over
                if (child.nodeName.toUpperCase() !== 'IMG') {
                    text = getTextFromNode(child);
                }
                // get innerText, if child is Node.TEXT_NODE and textTags is false or the node name presents in textTags
            } else if (nodeType === 3) {
                text = child.nodeValue;
            }

            if (text) {
                // Add space at text starting, if addSpaces is true
                //  and previous text ends with non-whitespace character
                //  and current text starts with non-whitespace character
                // Previous and Current not must be non text_node to add space
                if ((previousNodeType !== 3 || nodeType !== 3) && NON_WHITESPACE_END.test(result) && NON_WHITESPACE_START.test(text)) text = ' ' + text;
                result += text;
            }

            // Save node type in variable for next iteration
            previousNodeType = nodeType;
        }

        return result;
    }

    function getText() {
        // Get copy of current HTML
        const documentCopy = documentObject.cloneNode(true).documentElement;

        // Remove tags
        removeTags(documentCopy);

        let text = getTextFromNode(documentCopy).trim();

        // Return empty text immediately
        if (text === '') return '';

        text = sanitize(text);

        // Remove whitespace
        text = stripWhitespace(text);

        // Remove invisible characters
        if (text !== '') text = stripInvisibleChars(text);
        console.log(text)
        return text;
    }

    function getTitle() { return documentObject.title || '' };

    function getMetaDescription() {
        // Get meta tag with description
        const description = documentObject.querySelector('meta[name="description"]');  // No I18N

        // Return description, if it is not null, otherwise return ''
        return description ? description.getAttribute('content') || '' : '';
    }

    function getMetaKeywords() {
        // Get meta tag with description
        const keywords = documentObject.querySelector('meta[name="keywords"]');  // No I18N

        // Return keywords, if it is not null, otherwise return ''
        return keywords ? keywords.getAttribute('content') || '' : '';
    }

    function getLang() {
        try {
            // Get lang attribute from <html>
            const language = documentObject.documentElement.lang;

            if (language) return language;

            // Get lang from meta tag
            //  |= used to check equals/startswith "lang"
            //  i used for case insensitive
            const languageMeta = documentObject.querySelector('meta[name|="lang" i], meta[http-equiv="content-language" i]');  // No I18N

            return languageMeta ? languageMeta.getAttribute('content') || '' : '';

        } catch {
            return '';
        }
    }

    // Extract and return values
    return {
        'text': getText(),  // No I18N
        'title': getTitle().trim(),  // No I18N
        'metaKeywords': getMetaKeywords().trim(),  // No I18N
        'metaDescription': getMetaDescription().trim(),  // No I18N
        'lang': getLang().trim(),  // No I18N
        'status': 'success',  // No I18N
        'message': 'Data extracted successfully!',  // No I18N
        'url':window.location.href, //No I18N
        // runtime in ms
        'extractionTime': Math.round((performance.now() - START_TIME) * 100) / 100  // No I18N
    };
}

if (document.readyState === "loading") 
{
    document.addEventListener("DOMContentLoaded", getData());
} 
else 
{
    getData()
}

