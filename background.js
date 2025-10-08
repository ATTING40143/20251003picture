chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'startTranslation') {
    console.log('Received startTranslation message from popup.');

    // Get the current active tab
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0] && tabs[0].id) {
        const tabId = tabs[0].id;

        // TODO: This is where the main translation logic will be triggered.
        // For now, we'll just log that we are "starting" the process.

        console.log(`Injecting content script into tab: ${tabId}`);

        // Execute content.js in the active tab
        chrome.scripting.executeScript({
          target: { tabId: tabId },
          files: ['content.js']
        }).then(() => {
          console.log('Content script injected successfully.');
          // After injecting, send a message to the content script to start its work
          chrome.tabs.sendMessage(tabId, { action: 'extractText' });
        }).catch(err => console.error('Failed to inject content script:', err));

      } else {
        console.error('Could not get active tab.');
      }
    });
  }

  // Return true to indicate you wish to send a response asynchronously
  // (although we are not sending one back in this simplified version)
  return true;
});

console.log('Background script loaded.');