console.log('Content script loaded.');

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extractText') {
    console.log('Received extractText message from background script.');

    // TODO: This is where the logic to find and extract all translatable text from the DOM will go.
    // For now, we'll just log a placeholder message.
    console.log('Simulating text extraction...');

    // In the future, this will collect all text nodes and send them back to the background script.
    // For example:
    // const texts = Array.from(document.body.getElementsByTagName('*'))
    //   .flatMap(el => Array.from(el.childNodes))
    //   .filter(node => node.nodeType === Node.TEXT_NODE && node.nodeValue.trim())
    //   .map(node => node.nodeValue.trim());
    //
    // chrome.runtime.sendMessage({ action: 'textExtracted', data: texts });
  }
  return true; // Indicates an asynchronous response may be sent.
});