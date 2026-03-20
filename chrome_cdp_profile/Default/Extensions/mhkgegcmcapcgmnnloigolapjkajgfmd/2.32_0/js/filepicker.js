(function() {
  const original = window.showOpenFilePicker;
  if (!original) { return };

  let currentUrl = document.location.href !== undefined ? document.location.href : null;

  window.showOpenFilePicker = async function(...args) {
    // const handles = await original.apply(this, args);
    const handles = await original(...args);
    const requestId = Date.now() + Math.random(); // unique id

    try {
      const files = await Promise.all(handles.map(h => h.getFile()));
      window.postMessage({
        source: "file-picker-hook", //No I18N
        requestId,   // include id
        files: files.map(f => ({
          name: f.name,
          size: f.size,
          type: f.type,
          lastModified: f.lastModified
        }))
      }, currentUrl);
    } catch (err) {
    //   console.warn("[Extension] Error reading files:", err);    //No I18N
    }

    return new Promise((resolve, reject) => {
      function onDecision(event) {
        if (event.source !== window) { return };
        const msg = event.data;
        if (msg && msg.source === "file-picker-decision" && msg.requestId === requestId) {  //No I18N
          window.removeEventListener("message", onDecision);    //No I18N

          if (msg.block) {
            resolve([]); // block
          } else {
            resolve(handles); // allow
          }
        }
      }
      window.addEventListener("message", onDecision);   //No I18N
    });
  };

  //Hook showDirectoryPicker (folders)

  const originalDir = window.showDirectoryPicker;
  if (originalDir) {
    window.showDirectoryPicker = async function(...args) {
      // const dirHandle = await originalDir.apply(this, args);
      const dirHandle = await originalDir(...args);
      const requestId = Date.now() + Math.random();

      try {
        // Convert directory handle → fake file list with just the folder name
        window.postMessage({
          source: "file-picker-hook",   //No I18N
          pickerType: "directory", // distinguish   //No I18N
          requestId,
          files: [{
            name: dirHandle.name,
            size: 0,
            type: "folder", //No I18N
            lastModified: Date.now()
          }]
        }, currentUrl);
      } catch (err) {
        // console.warn("[Extension] Error reading directory:", err);  //No I18N
      }

      return new Promise((resolve) => {
        function onDecision(event) {
          if (event.source !== window) { return };
          const msg = event.data;
          if (msg && msg.source === "file-picker-decision" && msg.requestId === requestId) {    //No I18N
            window.removeEventListener("message", onDecision);  //No I18N

            if (msg.block) {
              resolve(null); // block (behaves like cancel)
            } else {
              resolve(dirHandle); // allow real directory handle
            }
          }
        }
        window.addEventListener("message", onDecision); //No I18N
      });
    };
  }
})();
