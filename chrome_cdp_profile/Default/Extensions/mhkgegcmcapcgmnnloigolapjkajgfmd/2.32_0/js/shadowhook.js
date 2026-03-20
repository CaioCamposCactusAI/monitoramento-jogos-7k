// Created by krishnan.saravanan — 03-Mar-2026
//
// shadowhook.js — Runs in MAIN world to intercept closed shadow roots
// and add file upload event listeners inside them AND their descendants.
//
// WHY THIS IS NEEDED:
// Content scripts (ISOLATED world) can discover open shadow roots via node.shadowRoot
// but CANNOT see through closed shadow boundaries (shadowRoot returns null).
// So any shadow root (open or closed) that is a descendant of a closed boundary
// is completely invisible to the content script.
//
// SOLUTION: This script intercepts ALL attachShadow calls. When a closed root is created,
// it processes that root AND recursively discovers all descendant shadow roots (open or closed).
// A 'change' listener is added to every discovered shadow root.

(function() {
    "use strict";   //No I18N

    // Idempotency guard: prevent double-patching when injected via both
    // registerContentScripts AND executeScript (e.g. in about:blank iframes)
    if (window.__bspShadowHookInstalled){ return; }
    window.__bspShadowHookInstalled = true;

    var originalAttachShadow = Element.prototype.attachShadow;
    if (!originalAttachShadow){ return; }

    // Track all shadow roots (open and closed) by their host element.
    var allShadowRoots = new WeakMap();
    // Track which shadow roots have already been processed (listeners added)
    var processedShadows = new WeakSet();
    var requestCounter = 0;

    Element.prototype.attachShadow = function(init) {
        var shadow = originalAttachShadow.call(this, init);
        allShadowRoots.set(this, shadow);

        if (init.mode === 'closed') {   //No I18N
            processShadowRoot(shadow);
        }
        return shadow;
    };

    function extractFiles(fileList) {
        var files = [];
        for (var i = 0; i < fileList.length; i++) {
            files.push({
                name: fileList[i].name,
                size: fileList[i].size,
                type: fileList[i].type,
                lastModified: fileList[i].lastModified
            });
        }
        return files;
    }

    // Process a shadow root: add file event listeners + MutationObserver + scan children
    function processShadowRoot(shadow) {
        if (processedShadows.has(shadow)){ return; }
        processedShadows.add(shadow);

        // Add 'change' listener in capture phase — fires BEFORE any target-phase page handler.
        shadow.addEventListener('change', function(event) {   //No I18N
            var el = event.target;
            if (!el || el.type !== 'file' || !el.files || el.files.length === 0){ return; }   //No I18N

            var files = extractFiles(el.files);
            var reqId = 'bsp-csf-' + (++requestCounter) + '-' + Date.now();   //No I18N
            var root = document.documentElement;

            // Write file metadata to DOM attribute for uploadmanager.js to read
            root.setAttribute('data-bsp-req', JSON.stringify({   //No I18N
                requestId: reqId,
                files: files,
                url: window.location.href
            }));
            // Clear any previous decision
            root.removeAttribute('data-bsp-dec');   //No I18N

            // Dispatch synchronous custom event — uploadmanager.js (ISOLATED world)
            // listens for this, evaluates rules, and writes decision to data-bsp-dec.
            // dispatchEvent() is SYNCHRONOUS — the listener runs and returns before
            // this line completes. So data-bsp-dec is available immediately after.
            root.dispatchEvent(new CustomEvent('bsp-shadow-eval'));   //No I18N

            // Read the decision written by uploadmanager.js
            var decision = root.getAttribute('data-bsp-dec');   //No I18N

            // Clean up DOM attributes
            root.removeAttribute('data-bsp-req');   //No I18N
            root.removeAttribute('data-bsp-dec');   //No I18N

            if (decision === 'block') {   //No I18N
                // BLOCKED — clear input in the SAME event tick, before page handlers fire.
                try { el.value = ''; } catch(e) {}   //No I18N
                return;
            }

            // decision === 'allow' or null (uploadmanager.js not ready yet)
            // If null, event flows naturally — worst case is unblocked upload, but this
            // only happens in the brief window before uploadmanager.js initializes.
        }, true);

        // Observe for dynamically added children (async rendering like Lit/Polymer).
        var observer = new MutationObserver(function(mutations) {
            for (var i = 0; i < mutations.length; i++) {
                var added = mutations[i].addedNodes;
                for (var j = 0; j < added.length; j++) {
                    if (added[j].nodeType === Node.ELEMENT_NODE) {
                        scanForShadowRoots(added[j]);
                    }
                }
            }
        });
        observer.observe(shadow, { childList: true, subtree: true });

        scanForShadowRoots(shadow);
    }

    function scanForShadowRoots(root) {
        try {
            checkAndProcess(root);
            var elements = root.querySelectorAll ? root.querySelectorAll('*') : [];
            for (var i = 0; i < elements.length; i++) {
                checkAndProcess(elements[i]);
            }
        } catch(e) {}
    }

    function checkAndProcess(el) {
        var shadow = el.shadowRoot || allShadowRoots.get(el);
        if (shadow) {
            processShadowRoot(shadow);
        }
    }
})();