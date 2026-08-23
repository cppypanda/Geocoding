import { getApiName, formatConfidence, formatCoordinatesHtml, getApiMarkerHtml, logToConsole, createAndAppendElement, buildTableRows, showLoading, hideLoading, showToast, addMarkersToMapAndFitBounds, getMarkerIcon, convertCoordinates, loadLocationTypeSuffixes, stripLocationTypeSuffix, escapeHtml } from './utils.js';
import { showLocationOnMap, clearSearchMarkers as clearMapMarkers } from './map.js';
import { performSmartSearch, reverseGeocode, autoSelectPoint, performMapSearch } from './api.js';
import { clearMapSearchResults } from './ui.js';

// This is a large, self-contained module for the entire calibration panel.
let state = {
    // External dependencies
    itemCalibrationMap: null,
    onResultChanged: null, // Callback to notify main script of data changes
    currentUser: null, // Add currentUser to state

    // Internal state
    currentResultData: null, // The full data for the row being calibrated
    currentIndex: -1, // Current index in the results array
    mapSearchResults: [],
    mapSearchMarkers: [],
    apiResultMarkers: [],
    selectedResultMarker: null,
    manualSelectMarker: null,
    selectedPoiIndex: null, // 记录选中的POI索引
    isManualMarkMode: false,
    currentAdminDistrict: '', // For smart search context
    apiMarkersGroup: null, // 新增：用于管理候选标记点的图层组
    // 关键词锁定（针对当前记录生效）
    isKeywordLocked: false,
    keywordLockRecordIndex: null,
    
    // 地址级别的状态存储
    addressStates: new Map(), // 存储每个地址的POI搜索结果和网络信息
};


// --- 地址状态管理函数 ---

function saveAddressState(address, index) {
    if (!address) return;
    
    const stateKey = `${address}_${index}`;
    state.addressStates.set(stateKey, {
        mapSearchResults: [...state.mapSearchResults],
        selectedPoiIndex: state.selectedPoiIndex,
        mapSearchInput: document.getElementById('mapSearchInput')?.value || '',
        lastSearchKeyword: document.getElementById('mapSearchInput')?.value || '',
        timestamp: Date.now()
    });
    
    // console.log(`💾 已保存地址状态: ${stateKey}`, state.addressStates.get(stateKey));
}

function restoreAddressState(address, index) {
    if (!address) return false;
    
    const stateKey = `${address}_${index}`;
    const savedState = state.addressStates.get(stateKey);
    
    if (savedState) {
        // console.log(`📥 恢复地址状态: ${stateKey}`, savedState);
        
        // 恢复POI搜索结果
        state.mapSearchResults = [...savedState.mapSearchResults];
        state.selectedPoiIndex = savedState.selectedPoiIndex;
        
        // 恢复搜索输入框
        const mapSearchInput = document.getElementById('mapSearchInput');
        if (mapSearchInput && savedState.mapSearchInput) {
            mapSearchInput.value = savedState.mapSearchInput;
        }
        
        return true;
    }
    
    // console.log(`📭 未找到地址状态: ${stateKey}`);
    return false;
}

function clearAddressState(address, index) {
    if (!address) return;
    
    const stateKey = `${address}_${index}`;
    state.addressStates.delete(stateKey);
    // console.log(`🗑️ 已清除地址状态: ${stateKey}`);
}

// --- UI Update Functions ---

function isKeywordLockActiveForCurrent() {
    return !!(state.isKeywordLocked && state.keywordLockRecordIndex === state.currentIndex);
}

function setMapSearchInputValueSafely(value) {
    const inputEl = document.getElementById('mapSearchInput');
    if (!inputEl) return;
    if (isKeywordLockActiveForCurrent()) return; // 保持建议关键词不被覆盖
    inputEl.value = value;
}

function render() {
    if (!state.currentResultData) {
        hidePanel();
        return;
    }
    updateSelectedResultDetailCard();
    updateApiResultCards();
    updateCalibrationMapMarkers();
}

function updateSelectedResultDetailCard() {
    // This function updates the top-left card showing the currently selected result.
    const resultData = state.currentResultData;
    const card = document.getElementById('selectedResultDetailCard');
    const noSelectedMsg = document.getElementById('noSelectedResultMsg');
    if (!card || !noSelectedMsg) return;

    if (resultData && resultData.selected_result && resultData.selected_result.result) {
        card.style.display = 'block';
        noSelectedMsg.style.display = 'none';
        const sel = resultData.selected_result;
        const selRes = sel.result;

        document.getElementById('selectedPoiName').textContent = selRes.name || '-';
        document.getElementById('selectedFormattedAddress').textContent = selRes.formatted_address || '未知地址';
        document.getElementById('selectedSourceApi').textContent = getApiName(sel.api || sel.source_api || '未知');
        document.getElementById('selectedConfidence').innerHTML = formatConfidence(sel.confidence);
        document.getElementById('selectedWgs84').textContent = (typeof selRes.latitude_wgs84 === 'number') ? `${selRes.longitude_wgs84.toFixed(6)}, ${selRes.latitude_wgs84.toFixed(6)}` : '-';
        document.getElementById('selectedGcj02').textContent = (typeof selRes.latitude_gcj02 === 'number') ? `${selRes.longitude_gcj02.toFixed(6)}, ${selRes.latitude_gcj02.toFixed(6)}` : '-';
        document.getElementById('selectedLlmReason').textContent = sel.llm_reason || sel.selection_method_note || '-';
        
        const confirmBtn = document.getElementById('confirmCurrentBtn');
        if (confirmBtn) {
            const isConfirmed = resultData.confirmed || false;
            confirmBtn.classList.toggle('btn-success', isConfirmed);
            confirmBtn.classList.toggle('btn-outline-success', !isConfirmed);
            const icon = confirmBtn.querySelector('i');
            if(icon){
                icon.classList.toggle('bi-check-circle-fill', isConfirmed);
                icon.classList.toggle('bi-check-circle', !isConfirmed);
            }
        }
    } else {
        card.style.display = 'none';
        noSelectedMsg.style.display = 'block';
    }
}

function updateApiResultCards() {
    // This function updates the three cards for Amap, Baidu, Tianditu results.
    const resultData = state.currentResultData;
    if (!resultData || !Array.isArray(resultData.api_results)) return;
    document.querySelectorAll('.api-result-card').forEach(card => {
        const api = card.getAttribute('data-api');
        const contentDiv = card.querySelector('.result-content');
        const selectButton = card.querySelector('.select-api-btn');
        const apiResForCard = resultData.api_results.find(r => r.api === api);

        if (apiResForCard && apiResForCard.result) {
            const res = apiResForCard.result;
            const lat = res.latitude_wgs84;
            const lng = res.longitude_wgs84;

            // 针对百度和天地图，如果地址无效，则显示经纬度和Level
            if ((api === 'baidu' || api === 'tianditu') && (!res.formatted_address || res.formatted_address === state.currentResultData.address)) {
                 contentDiv.innerHTML = `
                    <p class="mb-1"><strong>地址:</strong> -</p>
                    <p class="mb-1"><strong>类型:</strong> ${escapeHtml(res.level || 'N/A')}</p>
                    <p class="mb-1 text-muted small"><strong>WGS84:</strong> ${lng?.toFixed(6)}, ${lat?.toFixed(6)}</p>
                `;
            } else if (res.formatted_address) {
                // 对于高德或有有效地址的其他服务商
            const district = res.district || res.county || '';
            const city = res.city || '';
            const province = res.province || '';
            let fullAdminArea = `${province}${city}${district}`;
            let displayAddress = res.formatted_address.startsWith(fullAdminArea) ? res.formatted_address : `${fullAdminArea} ${res.formatted_address}`;

            contentDiv.innerHTML = `
                <p class="mb-1"><strong>地址：</strong>${escapeHtml(displayAddress)}</p>
                    <p class="mb-1 text-muted small"><strong>WGS84:</strong> ${lng?.toFixed(6)}, ${lat?.toFixed(6)}</p>
            `;
            } else {
                 contentDiv.innerHTML = '<p class="text-muted">无有效结果</p>';
            }

            const isSelected = (resultData.selected_result && resultData.selected_result.api === api);
            selectButton.disabled = isSelected;
            selectButton.innerHTML = isSelected ? '<i class="bi bi-check"></i> 已选定' : '<i class="bi bi-check-lg"></i> 选定';
            selectButton.classList.toggle('btn-success', isSelected);
            selectButton.classList.toggle('btn-outline-success', !isSelected);
            

        } else {
            contentDiv.innerHTML = '<p class="text-muted">无结果</p>';
            selectButton.disabled = true;
            selectButton.innerHTML = '选定';
            selectButton.classList.remove('btn-success');
            selectButton.classList.add('btn-outline-success');
        }
    });
}

function updateCalibrationMapMarkers() {
    // This function clears and redraws ALL markers on the calibration map.
    if (!state.itemCalibrationMap) return;
    const map = state.itemCalibrationMap;
    const advancedContainer = document.getElementById('advancedApiResultsContainer');
    const isAdvancedVisible = advancedContainer && advancedContainer.classList.contains('show');

    // 清理旧的标记
    if (state.selectedResultMarker) map.removeLayer(state.selectedResultMarker);
    if (state.apiMarkersGroup) state.apiMarkersGroup.clearLayers();
    
    state.selectedResultMarker = null;
    if (!state.apiMarkersGroup) {
        state.apiMarkersGroup = L.layerGroup();
    }

    const allPoints = [];
    let selectedPoint = null;

    // 始终创建所有API候选标记，但将它们添加到图层组中
    state.currentResultData.api_results.forEach(apiRes => {
        if (apiRes && apiRes.result && typeof apiRes.result.latitude_gcj02 === 'number') {
            const lat = apiRes.result.latitude_gcj02;
            const lng = apiRes.result.longitude_gcj02;
            const html = getApiMarkerHtml(apiRes.api);
            
            const marker = L.marker([lat, lng], {
                icon: L.divIcon({
                    className: 'custom-div-icon', 
                    html: html,
                    iconSize: [24, 24], 
                    iconAnchor: [12, 12]
                })
            });

            marker.bindPopup(`<h6>${escapeHtml(getApiName(apiRes.api))}</h6><p>${escapeHtml(apiRes.result.formatted_address || '未知')}</p>`);
            marker.on('mouseover', function (e) { this.openPopup(); });
            marker.on('mouseout', function (e) { this.closePopup(); });
            marker.on('click', function() {
                state.currentResultData.selected_result = { ...apiRes, selection_method_note: '用户通过地图标记点选定' };
                if (state.onResultChanged) state.onResultChanged(state.currentResultData, state.currentIndex);
                render();
            });

            state.apiMarkersGroup.addLayer(marker); // 添加到图层组
            if (isAdvancedVisible) allPoints.push([lat, lng]);
        }
    });

    // 根据折叠状态显示/隐藏候选点图层组
    if (isAdvancedVisible) {
        state.apiMarkersGroup.addTo(map);
    } else {
        try { map.removeLayer(state.apiMarkersGroup); } catch (e) {}
    }

    // 始终绘制“当前选定结果”标记
    if (state.currentResultData.selected_result && typeof state.currentResultData.selected_result.result.latitude_gcj02 === 'number') {
        const sel = state.currentResultData.selected_result;
        const selRes = sel.result;
        
        const selectedIcon = getMarkerIcon(sel.confidence);

        state.selectedResultMarker = L.marker([selRes.latitude_gcj02, selRes.longitude_gcj02], { icon: selectedIcon }).addTo(map);
        
        state.selectedResultMarker.bindPopup(createSelectedResultPopupHtml(sel)).openPopup();
        allPoints.push([selRes.latitude_gcj02, selRes.longitude_gcj02]);
        selectedPoint = [selRes.latitude_gcj02, selRes.longitude_gcj02];
    }
    
    // 视野与动画：
    // - 折叠关闭：仅围绕“选定结果”平滑居中
    // - 折叠展开：平滑飞行到包含三方候选点与选定结果的范围
    try {
        if (isAdvancedVisible) {
            if (allPoints.length > 0) {
                if (typeof map.flyToBounds === 'function') {
                    map.flyToBounds(allPoints, { padding: [50, 50], maxZoom: 16, duration: 0.6 });
                } else {
                    map.fitBounds(allPoints, { padding: [50, 50], maxZoom: 16 });
                }
            }
        } else if (selectedPoint) {
            const targetZoom = 16;
            if (typeof map.flyTo === 'function') {
                map.flyTo(selectedPoint, targetZoom, { animate: true, duration: 0.5 });
            } else {
                try { map.setView(selectedPoint, targetZoom, { animate: true }); } catch (e) { map.setView(selectedPoint, targetZoom); }
            }
        }
    } catch (e) {
        // 回退：若动画失败，不影响基本显示
    }
}

// --- Smart Search (Address Analysis) ---
async function handleSmartSearch() {
    const searchInput = document.getElementById('searchInput');
    const query = searchInput.value.trim();
    if (!query) return;
    
    showLoading("智能分析中...");
    try {
        const selectedMode = document.querySelector('input[name="smartSearchMode"]:checked').value || 'crawl_extract';
        const data = await performSmartSearch(query, selectedMode);
        displaySmartSearchResults(data);
    } catch (error) {
        showToast('智能分析失败: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

function displaySmartSearchResults(data) {
    const table = document.getElementById('searchResultsTable');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    if (!data || !data.results || data.results.length === 0 || !data.results[0].description) {
        tbody.innerHTML = '<tr><td colspan="3" class="text-center">未找到相关结果或结果描述为空</td></tr>';
        return;
    }
    const description = data.results[0].description;
    const entries = description.split(/(?=\d+\.\s*地点：)/).filter(entry => entry.trim());
    const lines = description.split('\n');
    const adminLineIndex = lines.findIndex(line => line.trim().startsWith('行政区：'));
    const adminMatch = adminLineIndex !== -1 ? lines[adminLineIndex].match(/行政区：(.+)/) : null;
    state.currentAdminDistrict = adminMatch ? adminMatch[1].trim() : '';

    tbody.innerHTML = ''; // Clear previous results
    entries.forEach((entry, index) => {
        const locationMatch = entry.match(/地点：([^\n]+)/);
        const relationMatch = entry.match(/关系：([\s\S]+?)(?=\d+\.\s*地点：|\d+\.\s*关系：|行政区：|$)/); 
        if (locationMatch && relationMatch) {
            const locations = locationMatch[1].trim().split(/[，,、]/);
            const relation = escapeHtml(relationMatch[1].trim()).replace(/\n/g, '<br>');
            const locationTags = locations.map(loc => {
                const safeLocation = escapeHtml(loc.trim());
                return `<span class="location-tag" data-location="${safeLocation}">${safeLocation}</span>`;
            }).join('');
            tbody.innerHTML += `<tr><td class="text-center">${index + 1}</td><td>${locationTags}</td><td>${relation}</td></tr>`;
        }
    });
}


// --- Map Search ---
async function handleMapSearch(searchTerm, source = 'amap', sourceContext) {
    const mapSearchSpinner = document.getElementById('mapSearchSpinner');
    if(mapSearchSpinner) mapSearchSpinner.style.display = 'block';

    try {
        const data = await performMapSearch(searchTerm, source);
        // Backend now returns a unified format under 'results' or 'pois'
        state.mapSearchResults = data.results || data.pois || [];
        try {
            const sample = (state.mapSearchResults || []).slice(0, 3);
        } catch (e) {}
        state.mapSearchResults.llmSourceContext = sourceContext; // Attach context

        // --- BUG FIX ---
        // The following block contained a faulty client-side confidence calculation
        // that overwrote the correct score from the backend. It has been removed.
        // The system will now exclusively use the 'confidence' property provided by the backend.
        
        state.selectedPoiIndex = null; // 重置选中索引
        displayMapSearchResults();

        // 保存当前地址的状态
        if (state.currentResultData && state.currentResultData.address) {
            saveAddressState(state.currentResultData.address, state.currentIndex);
        }

        // After displaying, try to auto/smart select a point
        // If no results, this will do nothing, which is fine.
        if (state.mapSearchResults.length > 0) {
            // This now runs, but the spinner will be hidden AFTER it completes.
            const result = await hybridSelectPointFromMapSearch();
            if(!result || !result.ok) {
                const reason = result && result.code === 'NEED_WEB_INFO'
                    ? '需要更多网络信息支撑'
                    : '没有高可信度候选';
                showToast(`POI智能选点未成功（${reason}）`, 'info');
            }
        }
        return { success: true, results: state.mapSearchResults };
    } catch (error) {
        showToast('地图搜索失败: ' + error.message, 'error');
        // Ensure map search results are cleared on error
        state.mapSearchResults = [];
        displayMapSearchResults();
        return { success: false, error: error.message };
    } finally {
        // The spinner is now controlled by the calling logic (smart calibration)
        // or hidden here AFTER the await hybridSelectPointFromMapSearch() completes.
        if(mapSearchSpinner) mapSearchSpinner.style.display = 'none';
    }
}

function displayMapSearchResults() {
    const table = document.querySelector('#mapSearchResultsTable');
    const tbody = document.querySelector('#mapSearchResultsTable tbody');
    const titleElement = document.getElementById('poi-results-title');
    
    if(!tbody) {
        return;
    }

    // 清理上一次创建的 POI 标记
    try {
        if (Array.isArray(state.mapSearchMarkers) && state.itemCalibrationMap) {
            state.mapSearchMarkers.forEach(m => {
                try { state.itemCalibrationMap.removeLayer(m); } catch (e) {}
            });
        }
    } catch (e) {}
    state.mapSearchMarkers = [];
    
    if (state.mapSearchResults.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center">未找到相关POI</td></tr>';
        if (titleElement) {
            titleElement.innerHTML = '地图搜索结果';
        }
        return;
    }

    // 根据结果更新标题
    if (titleElement && state.mapSearchResults[0] && state.mapSearchResults[0].source_display_name) {
        const sourceName = state.mapSearchResults[0].source_display_name;
        titleElement.innerHTML = `地图搜索结果 <small class="text-muted"> - ${escapeHtml(sourceName)}</small>`;
    } else if (titleElement) {
        titleElement.innerHTML = '地图搜索结果';
    }

    const allPoiPoints = [];
    tbody.innerHTML = '';
    
    state.mapSearchResults.forEach((poi, index) => {
        // console.log(`创建第${index + 1}行POI: ${poi.name}`);
        
        const lat = parseFloat(poi.latitude_gcj02 || poi.latitude);
        const lng = parseFloat(poi.longitude_gcj02 || poi.longitude);
        
        // 检查这个POI是否已被选中
        const isSelected = state.selectedPoiIndex === index;
        const buttonClass = isSelected ? 'btn btn-sm btn-success' : 'btn btn-sm btn-outline-success';
        const iconColor = isSelected ? 'text-white' : '';
        
        // 直接创建tr元素
        const row = document.createElement('tr');
        // --- BUG FIX ---
        // Directly use the backend-provided 'confidence' field.
        const confidenceDisplay = (typeof poi.confidence === 'number' && !isNaN(poi.confidence))
            ? `${(poi.confidence * 100).toFixed(1)}%`
            : '-';

        if (index === 0) {
            try {
            } catch (e) {}
        }
        row.innerHTML = `
            <td class="text-center">${index + 1}</td>
            <td><strong>${escapeHtml(poi.name)}</strong></td>
            <td><small>${escapeHtml(poi.address)}</small></td>
            <td><small>${escapeHtml(`${poi.pname || ''}${poi.cityname || ''}${poi.adname || ''}`)}</small></td>
            <td class="text-center">${confidenceDisplay}</td>
            <td class="text-center">
                <button class="${buttonClass}" data-action="select-poi" data-index="${index}">
                    <i class="bi bi-check-lg ${iconColor}"></i>
                </button>
            </td>
        `;
        
        // 添加到表格
        tbody.appendChild(row);
        // console.log(`已添加第${index + 1}行到表格`);
        
        if (!isNaN(lat) && !isNaN(lng)) {
            const html = `<div class="number-marker">${index + 1}</div>`;
            const marker = L.marker([lat, lng], {
                icon: L.divIcon({
                    className: 'custom-div-icon',
                    html: html,
                    iconSize: [26, 26],
                    iconAnchor: [13, 13]
                })
            }).addTo(state.itemCalibrationMap);
            marker.bindPopup(`<h6>${escapeHtml(poi.name)}</h6><p>${escapeHtml(poi.address)}</p>`);
            state.mapSearchMarkers.push(marker);
            allPoiPoints.push([lat, lng]);
        }
    });
    
    // 使用本次创建的标记计算并适配视野
    try {
    } catch (e) {}
}

// --- Point Selection Logic ---
async function hybridSelectPointFromMapSearch() {
    const originalAddress = document.getElementById('mapSearchInput').value.trim();
    if (!originalAddress || state.mapSearchResults.length === 0) {
        return { ok: false, code: 'NO_INPUT_OR_RESULTS' };
    }

    // --- NEW: High-Confidence Shortcut ---
    // Find the POI with the highest confidence score.
    const sortedResults = [...state.mapSearchResults].sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
    const bestMatch = sortedResults[0];

    if (bestMatch && typeof bestMatch.confidence === 'number' && bestMatch.confidence >= 0.90) {
        // Find the original index of the best match in the unsorted list to select it.
        const originalIndex = state.mapSearchResults.findIndex(poi => poi === bestMatch);
        
        if (originalIndex !== -1) {
            handleMapPoiSelection(originalIndex, '高置信度自动选定'); // Pass a specific reason
            showToast(`已自动选定高置信度匹配项: ${bestMatch.name}`, 'success');
            return { ok: true, code: 'CONFIDENCE_SHORTCUT' };
        }
    }
    // --- END: High-Confidence Shortcut ---

    try {
        let data = await autoSelectPoint(state.mapSearchResults, originalAddress, '地图搜索');
        
        if (data.success && data.result && data.result.index !== undefined) {
            
            // Pass the reason from the LLM response to the selection handler
            const reason = data.selected_poi ? data.selected_poi.llm_reason : 'LLM智能选定';
            handleMapPoiSelection(data.result.index, reason);
            return { ok: true, code: 'LLM_SUCCESS' };
        }

        const code = (data && data.message) || 'NO_HIGH_CONFIDENCE';
        return { ok: false, code };

    } catch (error) {
        // 当自动选点API本身抛出错误时（例如网络问题或内部错误），进行区分
        // 如果错误消息明确指出是“无高置信度”，则将其作为一种预期的业务逻辑“失败”，而非技术错误
        if (error && error.message && error.message.includes('NO_HIGH_CONFIDENCE')) {
            return { ok: false, code: 'NO_HIGH_CONFIDENCE' };
        }
        // 对于其他所有未知或网络错误，返回通用错误码
        return { ok: false, code: 'LLM_ERROR' };
    }
}


function handleMapPoiSelection(index, selectionReason = null) {
    // FIX: Update the internal state to track the selected POI index. This was missing.
    state.selectedPoiIndex = index;
    
    if (state.currentResultData) {
        const selectedPoi = state.mapSearchResults[index];
        if (!selectedPoi) {
            console.error(`handleMapPoiSelection: POI at index ${index} not found.`);
            return; // Exit if the selected POI is not found
        }

        // Update the main selected result object
        state.currentResultData.selected_result = {
            api: (selectedPoi.source_api || 'amap').replace('_poi', ''),
            confidence: selectedPoi.confidence,
            result: {
                ...selectedPoi, // copy all properties from poi
                formatted_address: selectedPoi.address,
                name: selectedPoi.name,
                latitude_gcj02: parseFloat(selectedPoi.latitude_gcj02),
                longitude_gcj02: parseFloat(selectedPoi.longitude_gcj02),
                latitude_wgs84: parseFloat(selectedPoi.latitude_wgs84),
                longitude_wgs84: parseFloat(selectedPoi.longitude_wgs84),
                province: selectedPoi.pname || '',
                city: selectedPoi.cityname || '',
                district: selectedPoi.adname || '',
            },
            selection_method_note: selectionReason || (state.mapSearchResults.llmSourceContext ? `地图搜索选点 (${state.mapSearchResults.llmSourceContext})` : '地图搜索选点')
        };
        
        // Also update the dedicated index property for state saving
        state.currentResultData.selected_map_poi_index = index;
    }
    
    // Notify the main script that the result has changed
    if (state.onResultChanged) {
        state.onResultChanged(state.currentResultData, state.currentIndex);
    }
    
    // Save the state for this address (including the selected POI) for caching
    if (state.currentResultData && state.currentResultData.address) {
        saveAddressState(state.currentResultData.address, state.currentIndex);
    }
    
    // Re-render the POI table to reflect the new selection (button styles)
    displayMapSearchResults();
    
    // Re-render the rest of the calibration panel (cards, map markers)
    render();
}


// --- Manual Marking ---

function toggleManualMarkMode() {
    state.isManualMarkMode = !state.isManualMarkMode;
    const manualMarkBtn = document.getElementById('manualMarkBtnOnMap'); // Fixed ID
    
    // Check if elements exist
    
    if (!manualMarkBtn) {
        showToast('手动标注按钮未找到', 'error');
        return;
    }
    
    if (!state.itemCalibrationMap) {
        showToast('地图未初始化', 'error');
        return;
    }
    
    const mapContainer = state.itemCalibrationMap.getContainer();

    if (state.isManualMarkMode) {
        manualMarkBtn.innerHTML = '<i class="bi bi-x-circle"></i> 取消手动选点';
        manualMarkBtn.classList.add('btn-danger');
        manualMarkBtn.classList.remove('btn-info');
        mapContainer.style.cursor = 'crosshair';
        showToast("手动选点已激活，请在地图上点击目标位置。", "info");
        state.itemCalibrationMap.on('click', onMapClickForManualMark);
    } else {
        manualMarkBtn.innerHTML = '<i class="bi bi-pin-map"></i> 手动选点';
        manualMarkBtn.classList.remove('btn-danger');
        manualMarkBtn.classList.add('btn-info');
        mapContainer.style.cursor = '';
        state.itemCalibrationMap.off('click', onMapClickForManualMark);
        if(state.manualSelectMarker) {
            state.itemCalibrationMap.removeLayer(state.manualSelectMarker);
            state.manualSelectMarker = null;
        }
    }
}

async function onMapClickForManualMark(e) {
    const { lat, lng } = e.latlng;
    
    if (state.manualSelectMarker) state.itemCalibrationMap.removeLayer(state.manualSelectMarker);
    state.manualSelectMarker = L.marker([lat, lng]).addTo(state.itemCalibrationMap)
        .bindPopup("正在获取位置信息...")
        .openPopup();

    showLoading('正在转换坐标并获取位置信息...');
    try {
        // Convert GCJ02 coordinates (from map) to WGS84 for API calls
        let wgs84Coords;
        try {
            wgs84Coords = await convertCoordinates(lng, lat, 'GCJ02', 'WGS84'); // Fix parameter order
        } catch (error) {
            console.warn('[Warning] Coordinate conversion failed, using original coordinates:', error.message);
            // Use original coordinates as fallback
            wgs84Coords = { latitude: lat, longitude: lng };
        }
        
        // Try reverse geocoding with WGS84 coordinates
        let reverseInfo = null;
        try {
            reverseInfo = await reverseGeocode(wgs84Coords.latitude, wgs84Coords.longitude);
            
            // Check if reverse geocoding actually succeeded
            if (!reverseInfo.success) {
                throw new Error(reverseInfo.error || 'Reverse geocoding returned failure');
            }
        } catch (error) {
            console.warn('[Warning] Reverse geocoding failed:', error.message);
            // Fallback to basic coordinates-based address
            reverseInfo = {
                success: true, // Mark as success for fallback case
                formatted_address: `手动选点 (${lat.toFixed(6)}, ${lng.toFixed(6)})`,
                address_components: {}
            };
        }

        // Safely access address components with fallbacks
        const addressComponents = reverseInfo.address_components || {};
        
        const selection = {
            api: 'manual_mark',
            confidence: 1,
            result: {
                formatted_address: reverseInfo.formatted_address || `手动选点 (${lat.toFixed(6)}, ${lng.toFixed(6)})`,
                name: '',
                latitude_gcj02: lat,
                longitude_gcj02: lng,
                latitude_wgs84: wgs84Coords.latitude,
                longitude_wgs84: wgs84Coords.longitude,
                province: addressComponents.province || '',
                city: addressComponents.city || '',
                district: addressComponents.district || '',
            },
            llm_reason: '用户手动地图点选'
        };

        state.currentResultData.selected_result = selection;
        if (state.onResultChanged) {
            state.onResultChanged(state.currentResultData, state.currentIndex);
        }
        
        // Re-render to update UI immediately
        render();
        
        // Update the marker popup with the final information
        if (state.manualSelectMarker) {
            state.manualSelectMarker.bindPopup(
                `<strong>手动选点成功</strong><br/>
                 <strong>地址:</strong> ${escapeHtml(selection.result.formatted_address)}<br/>
                 <strong>坐标:</strong> ${lng.toFixed(6)}, ${lat.toFixed(6)}`
            ).openPopup();
        }
        
        showToast('手动选点成功！', 'success');

    } catch (err) {
        console.error('[Error] Manual mark failed:', err);
        showToast('手动选点失败: ' + err.message, 'error');
        // Remove the marker if selection failed
        if (state.manualSelectMarker) {
            state.itemCalibrationMap.removeLayer(state.manualSelectMarker);
            state.manualSelectMarker = null;
        }
    } finally {
        hideLoading();
        toggleManualMarkMode(); // Deactivate after selection (success or failure)
    }
}


// --- Event Handlers ---
function setupEventListeners() {
    // Listener for the entire panel to delegate events
    const panel = document.getElementById('batchCalibrationResults');
    if (!panel) {
        return;
    }

    // 使用事件委托处理面板内的所有点击事件
    panel.addEventListener('click', (e) => {
        const button = e.target.closest('button');
        if(!button) return;

        // --- Card selection buttons ---
        const apiCard = e.target.closest('.api-result-card');
        if(apiCard) {
            const api = apiCard.dataset.api;
            const resultToSelect = state.currentResultData.api_results.find(r => r.api === api);
            if (resultToSelect) {
                state.currentResultData.selected_result = { ...resultToSelect, selection_method_note: '用户通过卡片选定' };
                if (state.onResultChanged) {
                    state.onResultChanged(state.currentResultData, state.currentIndex);
                }
                
                // Re-render to update UI immediately
                render();
            }
            return;
        }

        // --- Selected result detail card buttons ---
        if(button.id === 'locateSelectedOnMapBtn' && state.currentResultData.selected_result) {
            const selRes = state.currentResultData.selected_result.result;
            showLocationOnMap(state.itemCalibrationMap, selRes.latitude_gcj02, selRes.longitude_gcj02, selRes.formatted_address, createSelectedResultPopupHtml(state.currentResultData.selected_result));
            return;
        }
        if(button.id === 'clearSelectedInCardBtn') {
            state.currentResultData.selected_result = null;
            if (state.onResultChanged) {
                state.onResultChanged(state.currentResultData, state.currentIndex);
            }
            render(); // Re-render to update
            return;
        }
        if(button.id === 'confirmCurrentBtn') {
            if (state.currentResultData) {
                state.currentResultData.confirmed = !state.currentResultData.confirmed;
                
                button.classList.toggle('btn-success', state.currentResultData.confirmed);
                button.classList.toggle('btn-outline-success', !state.currentResultData.confirmed);
                const icon = button.querySelector('i');
                if(icon){
                    icon.classList.toggle('bi-check-circle-fill', state.currentResultData.confirmed);
                    icon.classList.toggle('bi-check-circle', !state.currentResultData.confirmed);
                }

                if (state.onResultChanged) {
                    state.onResultChanged(state.currentResultData, state.currentIndex);
                }
            }
            return;
        }
        
        // POI buttons are handled by separate event listener above
    });

    // 移除旧的事件监听器，改用全局 window.isPoiSearchLocked
    // try {
    //     window.addEventListener('poiSuggestionSearch', (ev) => {
    //         const kw = ev && ev.detail ? ev.detail.keyword : undefined;
    //         const inputEl = document.getElementById('mapSearchInput');
    //         if (inputEl && typeof kw === 'string') {
    //             state.isKeywordLocked = true;
    //             state.keywordLockRecordIndex = state.currentIndex;
    //             // 不在这里改值与触发搜索，由触发方负责；这里只做锁定标记
    //         }
    //     });
    // } catch (e) { /* ignore */ }

    // --- POI search results table event listener ---
    const mapSearchTable = document.getElementById('mapSearchResultsTable');
    if (mapSearchTable) {
        mapSearchTable.addEventListener('click', (e) => {
            const button = e.target.closest('button[data-action="select-poi"]');
            if (button) {
                const index = parseInt(button.dataset.index, 10);
                handleMapPoiSelection(index);
            }
        });
    }

    // --- Search buttons and inputs ---
    const smartSearchBtn = document.getElementById('smartSearchBtn');
    // const mapSearchBtn = document.getElementById('mapSearchBtn'); // This is now handled by map-search.js
    
    if (smartSearchBtn) {
        smartSearchBtn.addEventListener('click', handleSmartSearch);
    }
    
    /* This listener is now handled by the dedicated map-search.js module
    if (mapSearchBtn) {
        mapSearchBtn.addEventListener('click', async () => {
            const inputEl = document.getElementById('mapSearchInput');
            const source = document.getElementById('map-search-source')?.value;
            if (!inputEl) return;
            // 用户主动使用搜索按钮视为手动操作，不强制解锁；由输入事件决定解锁
            // Ensure suffix list is loaded once
            await loadLocationTypeSuffixes();
            const raw = (inputEl.value || '').trim();
            const cleaned = stripLocationTypeSuffix(raw).trim();
            if (cleaned && cleaned !== raw) {
                inputEl.value = cleaned; // reflect cleaned query in UI
            }
            if (cleaned) handleMapSearch(cleaned, source, '用户手动搜索');
        });
    }
    */

    // 用户手动输入时，解除锁定
    const mapSearchInput = document.getElementById('mapSearchInput');
    if (mapSearchInput) {
        mapSearchInput.addEventListener('input', () => {
            // state.isKeywordLocked = false;
            // state.keywordLockRecordIndex = null;
            window.isPoiSearchLocked = false;
        });
    }

    // 新增：监听“显示/隐藏”按钮的折叠事件
    const advancedResultsContainer = document.getElementById('advancedApiResultsContainer');
    if (advancedResultsContainer) {
        advancedResultsContainer.addEventListener('shown.bs.collapse', () => {
            if (state.itemCalibrationMap && state.apiMarkersGroup) {
                state.apiMarkersGroup.addTo(state.itemCalibrationMap);
            }
            // 展开后重绘并平滑过渡到三方候选范围
            try { updateCalibrationMapMarkers(); } catch (e) {}
        });
        advancedResultsContainer.addEventListener('hidden.bs.collapse', () => {
            if (state.itemCalibrationMap && state.apiMarkersGroup) {
                state.itemCalibrationMap.removeLayer(state.apiMarkersGroup);
            }
            // 收起后重绘并平滑过渡到“选定结果”
            try { updateCalibrationMapMarkers(); } catch (e) {}
        });
    }
    
    // Manual mark button event is handled by script.js, not here
    
    // --- Smart search results table listener ---
    const smartSearchResultsTbody = document.querySelector('#searchResultsTable tbody');
    if (smartSearchResultsTbody) {
        smartSearchResultsTbody.addEventListener('click', e => {
            if (e.target && e.target.closest('.location-tag')) {
                const location = e.target.closest('.location-tag').dataset.location;
                if (location) {
                    const searchTerm = state.currentAdminDistrict ? `${state.currentAdminDistrict}${location}` : location;
                    const mapSearchInput = document.getElementById('mapSearchInput');
                    if (mapSearchInput) {
                        setMapSearchInputValueSafely(searchTerm);
                        handleMapSearch(searchTerm, 'tianditu', `源自智能分析: '${location}'`);
                    }
                }
            }
        });
    }
}


// --- Public API ---
function showPanelFor(resultData, currentIndex, totalResults) {
    // First, check if a keyword lock is active from another record.
    // If the user clicks a new row, the lock from a previous keyword search should be cleared.
    if (window.isPoiSearchLocked && state.currentIndex !== currentIndex) {
        window.isPoiSearchLocked = false;
    }

    // 在保存之前的状态（如果需要）
    if (state.currentResultData && state.currentResultData.address && state.currentIndex >= 0) {
        saveAddressState(state.currentResultData.address, state.currentIndex);
    }

    state.currentResultData = resultData;
    state.currentIndex = currentIndex; // Save the current index
    document.getElementById('batchCalibrationResults').style.display = 'block';

    // Update the original address display
    const originalAddressElement = document.getElementById('originalAddressDisplay');
    if (originalAddressElement) {
        originalAddressElement.textContent = resultData.address || '无原始地址';
    }

    // Update the item indicator (e.g., "3 / 10")
    const indicator = document.getElementById('currentItemIndicatorInCard');
    if (indicator) {
        indicator.textContent = `(${currentIndex + 1} / ${totalResults})`;
    }
    
    // 尝试恢复当前地址的状态
    const hasRestoredState = restoreAddressState(resultData.address, currentIndex);
    
    // 如果没有恢复任何状态，则重置POI搜索相关状态
    if (!hasRestoredState) {
        state.mapSearchResults = [];
        state.selectedPoiIndex = null;
    }

    // 统一渲染POI面板（无论是否恢复了状态）
    displayMapSearchResults();

    // Reset inputs that are now part of the separate Address Search Tools panel
    const searchInput = document.getElementById('searchInput');
    if (searchInput) searchInput.value = '';
    
    const mapSearchInput = document.getElementById('mapSearchInput');
    if (mapSearchInput && !hasRestoredState) {
        // If a keyword search is active for this specific item, DO NOT overwrite the input.
        if (window.isPoiSearchLocked) {
            // Lock is active, do nothing to the input.
        } else {
            try {
                const base = resultData.address || '';
                const cleaned = stripLocationTypeSuffix(base);
                mapSearchInput.value = cleaned;
            } catch (e) {
                mapSearchInput.value = resultData.address;
            }
        }
    }

    // 恢复：仅同步"智能地址情报"输入框的默认值，不调用其模块方法
    const currentAnalysisInput = document.getElementById('currentAnalysisAddressInput');
    if (currentAnalysisInput) {
        currentAnalysisInput.value = resultData.address || '';
    }
    
    // 通知智能地址情报模块切换地址（如果模块存在的话）
    if (window.webIntelligence && resultData.address) {
        window.webIntelligence.setCurrentAddress(resultData.address, currentIndex);
    }

    // 已移除：不再向"智能地址情报"模块传递/同步地址与POI候选，避免跨模块DOM依赖

    render();
}

function hidePanel() {
    document.getElementById('batchCalibrationResults').style.display = 'none';
}

function setMap(mapInstance) {
    state.itemCalibrationMap = mapInstance;
    // If there's data loaded, it might need a redraw with the new map.
    if (state.currentResultData) {
        updateCalibrationMapMarkers();
    }
}

export function initializeCalibrationPanel(itemCalibrationMap, callbacks, currentUser) {
    state.itemCalibrationMap = itemCalibrationMap;
    state.onResultChanged = callbacks.onResultChanged;
    state.currentUser = currentUser;
    
    // Initial render
    render();
    
    // Setup event listeners for the panel's controls
    setupEventListeners();

    return {
        showPanelFor,
        hidePanel,
        setMap,
        toggleManualMarkMode, // Add missing function
        handleMapPoiSelection, // Expose this for main script to call
        isShowingResult: (index) => state.currentIndex === index, // Add helper for checking current index
        getAddressStates: () => Object.fromEntries(state.addressStates), // 返回状态数据供任务保存
        restoreAddressStates: (states) => { // 从任务恢复状态数据
            if (states && typeof states === 'object') {
                state.addressStates = new Map(Object.entries(states));
            }
        },
        setMapSearchResults: (results) => {
            state.mapSearchResults = results;
        },
        handleMapSearch // Expose the function for external use
    };
}

// Helper to create popup HTML, needed internally and by main script for map clicks
export function createSelectedResultPopupHtml(selectedResult) {
    if (!selectedResult || !selectedResult.result) return '';
    const result = selectedResult.result;
    return `<div class="popup-content selected-result-popup">
                <h6>${escapeHtml(result.formatted_address || '已选定位置')}</h6>
                <p><strong>来源：</strong> ${escapeHtml(getApiName(selectedResult.api || '未知'))}</p>
                <p><strong>可信度：</strong> ${formatConfidence(selectedResult.confidence)}</p>
                ${selectedResult.llm_reason ? `<p><strong>选点理由：</strong>${escapeHtml(selectedResult.llm_reason)}</p>` : ''}
                ${formatCoordinatesHtml(result)}
            </div>`;
}
