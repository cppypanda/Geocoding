import { showToast, showLoading, hideLoading } from './utils.js';

// Helper function to introduce a delay
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// Helper to click an element and wait a bit
async function clickElement(selector, waitTime = 50) {
    const element = document.querySelector(selector);
    if (element) {
        element.click();
        await sleep(waitTime);
        return true;
    }
    console.error(`[DEBUG] Element not found for selector: ${selector}`);
    return false;
}

// Helper to set value of a select element
function setSelectValue(selector, value) {
    const select = document.querySelector(selector);
    if (select) {
        select.value = value;
        select.dispatchEvent(new Event('change'));
        return true;
    }
    console.error(`[DEBUG] Select element not found for selector: ${selector}`);
    return false;
}

// Waits for a specific element to be visible and fully rendered.
function waitForElementVisible(selector, timeout = 5000) {
    return new Promise((resolve, reject) => {
        const startTime = Date.now();
        const interval = setInterval(() => {
            const element = document.querySelector(selector);
            if (element && element.offsetParent !== null) { // Check for visibility
                clearInterval(interval);
                resolve(element);
            } else if (Date.now() - startTime > timeout) {
                clearInterval(interval);
                reject(new Error(`[DEBUG] Timeout waiting for element ${selector} to become visible.`));
            }
        }, 100);
    });
}

// Helper function to wait for an element to exist in the DOM.
function waitForElementExists(selector, timeout = 5000) {
    return new Promise((resolve, reject) => {
        const interval = 100;
        let elapsedTime = 0;
        const timer = setInterval(() => {
            const element = document.querySelector(selector);
            if (element) {
                clearInterval(timer);
                resolve(element);
            } else {
                elapsedTime += interval;
                if (elapsedTime >= timeout) {
                    clearInterval(timer);
                    reject(new Error(`[DEBUG] Timeout waiting for element ${selector} to exist in the DOM.`));
                }
            }
        }, interval);
    });
}

// Waits for a Bootstrap collapse element to be fully shown using its events.
function waitForBootstrapCollapse(selector, timeout = 5000) {
    return new Promise((resolve, reject) => {
        const element = document.querySelector(selector);
        if (!element) {
            return reject(new Error(`[DEBUG] Bootstrap element not found for selector: ${selector}`));
        }

        // If it's already visible, resolve immediately.
        if (element.classList.contains('show')) {
            return resolve(element);
        }

        const timeoutId = setTimeout(() => {
            element.removeEventListener('shown.bs.collapse', handler);
            reject(new Error(`[DEBUG] Timeout waiting for Bootstrap element ${selector} to be shown.`));
        }, timeout);

        const handler = () => {
            clearTimeout(timeoutId);
            // No need to remove listener here as it's a one-time event (`once: true`)
            resolve(element);
        };

        // Listen for the specific event that fires after the transition is complete.
        element.addEventListener('shown.bs.collapse', handler, { once: true });
    });
}


// Waits for a spinner element to disappear.
function waitForSpinnerToDisappear(selector, timeout = 120000) { // Default timeout 2 minutes
    return new Promise((resolve, reject) => {
        const startTime = Date.now();
        const interval = setInterval(() => {
            const element = document.querySelector(selector);
            if (!element || element.style.display === 'none') {
                clearInterval(interval);
                resolve();
            } else if (Date.now() - startTime > timeout) {
                clearInterval(interval);
                reject(new Error(`[DEBUG] Timeout waiting for spinner ${selector} to disappear.`));
            }
        }, 500);
    });
}

// The core success checker: waits for the selected result card to update.
async function waitForResultUpdate(initialAddressText, timeout = 500) {
    console.log(`[DEBUG] Waiting for result update. Initial text: "${initialAddressText.substring(0, 20)}..."`);
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
        const card = document.querySelector('#selectedResultDetailCard');
        const currentAddressElement = document.querySelector('#selectedFormattedAddress');
        
        // Success condition: card is visible AND the address text has changed.
        if (card && card.style.display !== 'none' && currentAddressElement && currentAddressElement.textContent.trim() !== initialAddressText) {
            console.log(`[DEBUG] SUCCESS: Selected result card updated to "${currentAddressElement.textContent.trim().substring(0, 20)}..."`);
            return true;
        }
        await sleep(250); // Poll every 250ms
    }
    console.log('[DEBUG] TIMEOUT: Result card did not update within the time limit.');
    return false;
}


async function calibrateSingleAddress(row, rowIndex) {
    const originalAddress = row.querySelector('td:nth-child(2)').textContent.trim();
    console.log(`%c--- [DEBUG] Starting Calibration for row ${rowIndex + 1}: "${originalAddress}" ---`, 'color: blue; font-weight: bold;');

    try {
        // 2.1. Prepare
        console.log('[DEBUG] Step 2.1: Preparing panel...');
        const viewButton = row.querySelector('.btn-outline-primary');
        if (viewButton) viewButton.click();
        
        // Wait for the main panel to show up first
        await waitForElementVisible('#detailedReviewSection');
        
        // Then click the button to trigger the display of the tools panel
        await clickElement('#showAddressSearchToolsBtn');

        // The tools panel is a separate container. We need to wait for it to become visible.
        // The simplest check is for its `display` style property.
        await waitForElementVisible('#addressSearchToolsContainer');
        
        console.log('[DEBUG] Step 2.1: Panel ready.');
        
        const initialAddressElement = document.querySelector('#selectedFormattedAddress');
        const initialAddressText = initialAddressElement ? initialAddressElement.textContent.trim() : `__NO_INITIAL_RESULT_${Date.now()}__`;
        console.log(`[DEBUG] Step 2.1: Recorded initial selected address: "${initialAddressText}"`);

        // 2.2. POI Search Pole
        const poiSources = ['tianditu', 'amap', 'baidu'];
        for (const source of poiSources) {
            console.log(`[DEBUG] Step 2.2: Trying POI source: ${source.toUpperCase()}`);
            setSelectValue('#map-search-source', source);
            await clickElement('#mapSearchBtn');
            await waitForSpinnerToDisappear('#mapSearchSpinner');
            
            // --- NEW DEBUG LOGGING ---
            const results = window.poiResults || [];
            console.log(`[DEBUG] POI Search with ${source.toUpperCase()} returned ${results.length} results.`);
            if (results.length > 0) {
                // Log top 3 results for inspection
                const topResults = results.slice(0, 3).map(r => ({ name: r.name, address: r.address, confidence: r._confidence }));
                console.log('[DEBUG] Top 3 results:', JSON.stringify(topResults, null, 2));
            }
            // --- END NEW DEBUG LOGGING ---

            if (await waitForResultUpdate(initialAddressText)) {
                showToast(`地址 "${originalAddress}" 校准成功 (${source.toUpperCase()})`);
                return true;
            }
        }

        // 2.3. Keyword Suggestions
        console.log('[DEBUG] Step 2.3: POI search failed, trying keywords...');
        
        // Step A: Get Web Info
        console.log('[DEBUG] Step 2.3a: Getting web info...');
        await clickElement('#step1SearchBtn');
        await waitForSpinnerToDisappear('#step1Spinner', 120000); // 2 min timeout
        console.log('[DEBUG] Step 2.3a: Web info finished.');

        // Step B: Generate Keywords
        console.log('[DEBUG] Step 2.3b: Generating keywords...');
        await clickElement('#step3SuggestBtn');
        await waitForSpinnerToDisappear('#step3Spinner', 60000); // 1 min timeout
        console.log('[DEBUG] Step 2.3b: Keyword generation finished.');

        // Step C: Try Keywords
        const keywordButtons = document.querySelectorAll('.use-keyword-btn');
        if (keywordButtons.length > 0) {
            console.log(`[DEBUG] Step 2.3c: Found ${keywordButtons.length} keywords to try.`);
            setSelectValue('#map-search-source', 'tianditu'); // 新顺序：关键词优先用天地图
            for (const button of keywordButtons) {
                const keywordText = button.closest('.keyword-suggestion').querySelector('strong').textContent;
                console.log(`[DEBUG] Step 2.3c: Trying keyword: "${keywordText}"`);
                button.click();
                await waitForSpinnerToDisappear('#mapSearchSpinner');
                if (await waitForResultUpdate(initialAddressText)) {
                    showToast(`地址 "${originalAddress}" 校准成功 (关键词: ${keywordText})`);
                    return true;
                }
            }
        } else {
             console.log(`[DEBUG] Step 2.3c: No keywords were generated.`);
        }

        // 2.4. Final Failure
        console.log(`[DEBUG] FAILURE: All steps tried for "${originalAddress}", but no new result was selected.`);
        showToast(`地址 "${originalAddress}" 智能校准失败`, 'warning');
        return false;

    } catch (error) {
        console.error(`[DEBUG] FATAL ERROR during calibration for "${originalAddress}":`, error);
        showToast(`地址 "${originalAddress}" 校准失败: ${error.message}`, 'error');
        return false;
    }
}

export async function startSmartCalibration() {
    console.log("Starting Smart Calibration process...");
    showLoading("正在启动智能校准...");

    const resultsTableBody = document.querySelector('#cascadeResultsBody');
    if (!resultsTableBody) {
        hideLoading();
        showToast("无法找到结果列表。", "error");
        return;
    }

    const rows = Array.from(resultsTableBody.querySelectorAll('tr'));
    const rowsToCalibrate = rows.filter(row => {
        const confidenceCell = row.querySelector('td:nth-child(8) span');
        if (!confidenceCell) return false;
        const confidence = parseFloat(confidenceCell.textContent);
        return confidence < 90;
    });

    if (rowsToCalibrate.length === 0) {
        hideLoading();
        showToast("没有可信度低于90%的地址需要校准。", "info");
        return;
    }

    hideLoading();
    showToast(`发现 ${rowsToCalibrate.length} 条地址需要校准，流程开始...`, 'info');
    
    let successCount = 0;
    let failCount = 0;

    for (const row of rowsToCalibrate) {
        const rowIndex = rows.indexOf(row);
        const originalAddress = row.querySelector('td:nth-child(2)').textContent.trim();
        showLoading(`正在校准: ${originalAddress.substring(0, 15)}... (${successCount + failCount + 1}/${rowsToCalibrate.length})`);
        
        const success = await calibrateSingleAddress(row, rowIndex);
        if (success) {
            successCount++;
        } else {
            failCount++;
        }
        // Brief pause between addresses to allow UI to breathe
        await sleep(500);
    }
    
    hideLoading();
    showToast(`智能校准完成。成功: ${successCount}, 失败: ${failCount}`, 'success');

    // Smoothly scroll to the batch results processing section
    try {
        const target = document.getElementById('cascadeResultsContainer')
            || document.getElementById('detailedReviewSection')
            || document.getElementById('batchCalibrationResults');

        if (target && typeof target.scrollIntoView === 'function') {
            // Wait a bit to ensure layout/paint updates are complete
            setTimeout(() => {
                try {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    console.log('[DEBUG] Scrolled to batch results section after smart calibration.');
                } catch (e) {
                    // Fallback for environments without smooth scroll options
                    target.scrollIntoView();
                }
            }, 150);
        }
    } catch (e) {
        console.warn('[DEBUG] Failed to scroll to batch results section:', e);
    }
}
