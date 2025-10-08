import { performMapSearch, autoSelectPoint } from './api.js';
import { showToast, showLoading, hideLoading } from './utils.js';
import { displayMapSearchResults } from './ui.js';

let state = {
    map: null,
    currentMarker: null,
    poiResults: [],
    onPoiSelected: null,
    isPoiSearchLocked: false,
};

export function getPoiResults() {
    return state.poiResults;
}

async function handlePoiSearch() {
    const input = document.getElementById('mapSearchInput');
    const keyword = input.value.trim();
    const source = document.getElementById('map-search-source').value;

    if (!keyword) {
        showToast('请输入搜索关键词', 'warning');
        return;
    }

    const spinner = document.getElementById('mapSearchSpinner');
    if (spinner) spinner.style.display = 'inline-block';

    try {
        const data = await performMapSearch(keyword, source);
        
        if (data && Array.isArray(data.results) && data.results.length > 0) {
            state.poiResults = data.results;
            
            const tableBody = document.getElementById('map-search-results-body');
            
            // First, display the results as they are.
            displayMapSearchResults(tableBody, state.poiResults, keyword);
            window.poiResults = state.poiResults;

            // --- AUTO SELECTION LOGIC ---
            // After displaying, automatically try to select the best point.
            
            // 1. High-Confidence Shortcut
            const sortedResults = [...state.poiResults].sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
            const bestMatch = sortedResults[0];

            if (bestMatch && typeof bestMatch.confidence === 'number' && bestMatch.confidence >= 0.90) {
                if (state.onPoiSelected) {
                    state.onPoiSelected(bestMatch);
                    showToast(`已自动选定高置信度匹配项: ${bestMatch.name}`, 'success');
                }
            } else {
                // 2. If no high-confidence match, trigger LLM intelligent selection automatically.
                // This function will handle its own spinner and UI updates.
                showToast('无高置信度匹配项，尝试智能辅助决策...', 'info');
                // FIX: Pass the current search keyword to the intelligent select function.
                await handleIntelligentSelect(keyword);
            }
            // --- END AUTO SELECTION LOGIC ---

        } else {
            // This branch handles both API errors (data.success=false) and empty results arrays.
            showToast(data.message || '未找到相关地点', 'warning');
            state.poiResults = [];
            window.poiResults = [];
            displayMapSearchResults(document.getElementById('map-search-results-body'), [], keyword);
            if (spinner) spinner.style.display = 'none';
        }
    } catch (error) {
        showToast(error.message || '搜索POI时发生网络错误', 'error');
        if (spinner) spinner.style.display = 'none';
    } finally {
        if (spinner) {
            spinner.style.display = 'none';
        }
    }
}

function handleResultClick(e) {
    if (state.isPoiSearchLocked) {
        showToast('当前正在进行地址校准，POI搜索结果暂时锁定，请先完成或取消校准。', 'warning');
        return;
    }

    const row = e.target.closest('tr[data-poi-index]');
    if (!row) return;

    const selectedIndex = parseInt(row.dataset.poiIndex, 10);
    const selectedPoi = state.poiResults[selectedIndex];
    
    if (selectedPoi && state.onPoiSelected) {
        // Highlight the selected row
        const allRows = row.parentElement.querySelectorAll('tr');
        allRows.forEach(r => r.classList.remove('table-primary'));
        row.classList.add('table-primary');
        
        state.onPoiSelected(selectedPoi);
    }
    hideLoading();
}

async function handleIntelligentSelect(addressToUse = null) {
    if (!window.currentUser) {
        showToast('请先登录', 'warning');
        return;
    }

    // 新策略：前端不再进行积分预检查
    
    // FIX: Use the provided address if available, otherwise fall back to the display element.
    const originalAddress = addressToUse || document.getElementById('originalAddressDisplay').textContent;
    if (!originalAddress) {
        showToast('无法获取原始地址进行智能分析', 'error');
        return;
    }
    
    if (!state.poiResults || state.poiResults.length === 0) {
        showToast('没有可供智能选择的POI结果', 'warning');
        return;
    }

    const spinner = document.getElementById('mapSearchSpinner');
    if (spinner) spinner.style.display = 'inline-block';

    try {
        // FIX: Normalize the `tel` field in POI results to ensure consistent data type.
        const normalizedPoiResults = state.poiResults.map(poi => {
            let tel = poi.tel;
            if (Array.isArray(tel)) {
                tel = tel.join(', '); // Convert array to comma-separated string
            } else if (typeof tel !== 'string') {
                tel = ''; // Ensure it's always a string
            }
            return { ...poi, tel: tel };
        });

        const data = await autoSelectPoint(normalizedPoiResults, originalAddress, '地图搜索');
        // console.log('[DEBUG] 2. 收到API响应:', data);

        if (data.success && data.best_match) {
            const bestMatchIndex = data.best_match_index;
            // console.log('[DEBUG] 3. API返回成功，最佳匹配索引为:', bestMatchIndex);

            if (bestMatchIndex !== undefined && bestMatchIndex !== -1 && state.poiResults[bestMatchIndex]) {
                const selectedPoi = state.poiResults[bestMatchIndex];
                // console.log('[DEBUG] 4. 在当前POI列表中找到匹配项:', selectedPoi);
                
                if (state.onPoiSelected) {
                    // console.log('[DEBUG] 5. 准备调用onPoiSelected回调函数，将选择的POI传递给主脚本处理。');
                    state.onPoiSelected(selectedPoi);
                }
                showToast(`智能选择成功: ${selectedPoi.name}`, 'success');
                
            } else {
                // console.log('[DEBUG] 4a. 错误：API返回的索引在当前POI列表中无效。');
                showToast('智能选择返回了有效结果，但在当前列表中找不到匹配项', 'warning');
            }
        } else {
            // This is the case where the API call was successful but the LLM decided to abstain.
            // Check for the specific NO_HIGH_CONFIDENCE message.
            if (data.message && data.message.includes('NO_HIGH_CONFIDENCE')) {
                showToast('AI未能自动确定最佳匹配项，请手动选择或尝试“智能辅助校准”。', 'info');
            } else {
                showToast(data.message || '智能选择失败', 'error');
            }
        }
    } catch (error) {
        // This catches network errors or if the API throws an exception.
        // We now check if the thrown error's message is the one we want to handle gracefully.
        if (error && error.message && error.message.includes('NO_HIGH_CONFIDENCE')) {
            showToast('AI未能自动确定最佳匹配项，请手动选择或尝试“智能辅助校准”。', 'info');
        } else {
            showToast(`智能选择时发生错误: ${error.message || '未知错误'}`, 'error');
        }
    } finally {
        if (spinner) spinner.style.display = 'none';
    }
}

export function initializeMapSearch(map, onPoiSelectedCallback) {
    state.map = map;
    state.onPoiSelected = onPoiSelectedCallback;
    
    const searchBtn = document.getElementById('mapSearchBtn');
    const searchInput = document.getElementById('mapSearchInput');
    const resultsTableBody = document.getElementById('map-search-results-body');
    const intelligentSelectBtn = document.getElementById('intelligentSelectBtn');

    if (searchBtn) {
        searchBtn.addEventListener('click', handlePoiSearch);
    }
    if(searchInput) {
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                handlePoiSearch();
            }
        });
    }

    if (intelligentSelectBtn) {
        intelligentSelectBtn.addEventListener('click', handleIntelligentSelect);
    }

    if (resultsTableBody) {
        resultsTableBody.addEventListener('click', (e) => {
            const selectBtn = e.target.closest('.select-poi-btn');
            if (selectBtn) {
                handleResultClick(e);
            }
        });
    }
}

export function lockPoiSearch() {
    state.isPoiSearchLocked = true;
    const overlay = document.getElementById('poi-search-overlay');
    if (overlay) {
        overlay.style.display = 'flex';
    }
}

export function unlockPoiSearch() {
    state.isPoiSearchLocked = false;
    const overlay = document.getElementById('poi-search-overlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}
