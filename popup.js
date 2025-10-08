document.addEventListener('DOMContentLoaded', () => {
  const apiKeyInput = document.getElementById('apiKey');
  const sourceLangSelect = document.getElementById('sourceLang');
  const targetLangSelect = document.getElementById('targetLang');
  const translateBtn = document.getElementById('translateBtn');
  const autoTranslateCheckbox = document.getElementById('autoTranslate');

  // Load saved settings from chrome.storage
  chrome.storage.sync.get(['apiKey', 'sourceLang', 'targetLang', 'autoTranslate'], (result) => {
    if (result.apiKey) {
      apiKeyInput.value = result.apiKey;
    }
    if (result.sourceLang) {
      sourceLangSelect.value = result.sourceLang;
    } else {
      // Default value
      sourceLangSelect.value = 'auto';
    }
    if (result.targetLang) {
      targetLangSelect.value = result.targetLang;
    } else {
      // Default value
      targetLangSelect.value = 'zh-TW';
    }
    if (result.autoTranslate) {
      autoTranslateCheckbox.checked = result.autoTranslate;
    }
  });

  // Save API Key when it changes
  apiKeyInput.addEventListener('change', () => {
    chrome.storage.sync.set({ apiKey: apiKeyInput.value });
  });

  // Save Source Language when it changes
  sourceLangSelect.addEventListener('change', () => {
    chrome.storage.sync.set({ sourceLang: sourceLangSelect.value });
  });

  // Save Target Language when it changes
  targetLangSelect.addEventListener('change', () => {
    chrome.storage.sync.set({ targetLang: targetLangSelect.value });
  });

  // Save Auto-translate setting when it changes
  autoTranslateCheckbox.addEventListener('change', () => {
    chrome.storage.sync.set({ autoTranslate: autoTranslateCheckbox.checked });
  });

  // Handle Translate button click
  translateBtn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'startTranslation' });
    window.close(); // Close the popup
  });
});