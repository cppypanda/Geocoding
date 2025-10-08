import { getApiName, getApiBadgeColor, formatConfidence, formatCoordinatesHtml, buildTableRows } from './utils.js';

/**
 * Creates the HTML for action buttons in a table row.
 * This function is intended for internal use within the UI module.
 */
function createActionButtons(apiResult, rowIndex, isSelectedResult = false) {
    if (!apiResult || !apiResult.result) {
        return '-';
    }
    
    if (typeof apiResult.result.latitude_gcj02 !== 'number' || 
        typeof apiResult.result.longitude_gcj02 !== 'number') {
        return '-';
    }

    const lat_gcj02 = apiResult.result.latitude_gcj02;
    const lng_gcj02 = apiResult.result.longitude_gcj02;
    
    // 确保 formatted_address 是字符串
    let formattedAddress = '';
    if (apiResult.result.formatted_address !== null && apiResult.result.formatted_address !== undefined) {
        formattedAddress = String(apiResult.result.formatted_address);
    }
    const addr = formattedAddress.replace(/'/g, "\\'");

    const popup_details_raw_html = formatCoordinatesHtml(apiResult.result);
    const popup_details_escaped_for_onclick = popup_details_raw_html.replace(/'/g, "\\'");

    // 读取当前行的确认状态（从全局 currentResults 安全获取）
    let isConfirmed = false;
    try {
        if (Array.isArray(window.currentResults) && window.currentResults[rowIndex]) {
            isConfirmed = !!window.currentResults[rowIndex].confirmed;
        }
    } catch (e) {}

    const confirmBtnClass = isConfirmed ? 'btn-success' : 'btn-outline-success';
    const confirmIcon = isConfirmed ? 'bi-check-circle-fill' : 'bi-check-circle';

    // These onclick handlers call functions exposed on the window object in script.js
    return `
        <div class="btn-group btn-group-sm">
            <button class="btn btn-outline-primary" onclick="window.showItemInDetailedView(${rowIndex})" title="逐条校准"><i class="bi bi-card-list"></i></button>
            <button class="btn ${confirmBtnClass}" onclick="window.toggleRowConfirmation(${rowIndex})" title="确认/取消确认"><i class="bi ${confirmIcon}"></i></button>
            ${!isSelectedResult ?
                `<button class="btn btn-outline-success" onclick=\"window.selectResult(${rowIndex}, '${apiResult.api}')\"><i class=\"bi bi-check-lg\"></i></button>` :
                `<button class=\"btn btn-outline-danger\" onclick=\"window.clearSelectedResult(${rowIndex})\"><i class=\"bi bi-x-lg\"></i></button>`
            }
        </div>`;
}

/**
 * Renders the main cascade results table into a given tbody element.
 * @param {HTMLElement} tbody - The tbody element to populate.
 * @param {Array} data - The array of result data to render.
 * @param {number} [highlightIndex=-1] - The index of the row to highlight.
 */
export function displayCascadeResults(tbody, data, highlightIndex = -1, indexOffset = 0) {
    // console.log('🎯 displayCascadeResults 被调用');
    // console.log('  tbody:', tbody);
    // console.log('  data:', data);
    // console.log('  data.length:', Array.isArray(data) ? data.length : 'not array');
    
    if (!tbody) {
        console.error('❌ Table body for cascade results not provided.');
        return;
    }
    if (!Array.isArray(data)) { 
        console.error('❌ Cascade results data is not an array:', typeof data);
        tbody.innerHTML = '<tr><td colspan="11">数据格式错误</td></tr>';
        return; 
    }
    
    // console.log('✅ 开始渲染', data.length, '条结果到表格');

    // Use the generic buildTableRows helper
    buildTableRows(tbody, data, (result, index) => {
        const selectedResult = result.selected_result;

        // Safely access properties from the selectedResult
        let displaySelectedFormattedAddress = '-';
        let displaySelectedApiName = '-';
        let displaySelectedConfidence = '-';
        let displaySelectedLlmReason = '-';
        let displaySelectedActionButtons = '-';
        let displaySelectedProvince = '-';
        let displaySelectedCity = '-';
        let displaySelectedDistrict = '-';
        let displaySelectedWgs84Coords = '-';

        if (selectedResult && selectedResult.result) {
            const sr = selectedResult.result;
            displaySelectedFormattedAddress = sr.formatted_address || sr.name || '未知地址';
            displaySelectedApiName = `<span class="badge ${getApiBadgeColor(selectedResult.api || selectedResult.source_api)}">${getApiName(selectedResult.api || selectedResult.source_api || '未知')}</span>`;
            displaySelectedConfidence = formatConfidence(selectedResult.confidence);
            displaySelectedLlmReason = selectedResult.llm_reason || selectedResult.selection_method_note || '-';
            displaySelectedProvince = sr.province || '-';
            displaySelectedCity = sr.city || '-';
            displaySelectedDistrict = sr.district || sr.county || '-';
            
            if (typeof sr.latitude_wgs84 === 'number' && typeof sr.longitude_wgs84 === 'number') {
                displaySelectedWgs84Coords = `${sr.longitude_wgs84.toFixed(6)}, ${sr.latitude_wgs84.toFixed(6)}`;
            } else {
                displaySelectedWgs84Coords = '未知WGS84';
            }
            
            const mockApiResultForButton = { 
                result: { ...sr }, 
                api: selectedResult.api || selectedResult.source_api || 'selected' 
            };
            displaySelectedActionButtons = createActionButtons(mockApiResultForButton, index + indexOffset, true);

        } else if (selectedResult) {
            displaySelectedFormattedAddress = selectedResult.name || selectedResult.address || '结果异常';
            displaySelectedApiName = `<span class="badge ${getApiBadgeColor(selectedResult.api || 'unknown')}">${getApiName(selectedResult.api || 'unknown')}</span>`;
        }

        return `
            <td class="text-center">${index + 1 + indexOffset}</td>
            <td><div class="address-cell-content">${result.address}</div></td> 
            <td>${displaySelectedProvince}</td>
            <td>${displaySelectedCity}</td>
            <td>${displaySelectedDistrict}</td>
            <td><div class="address-cell-content">${displaySelectedFormattedAddress}</div></td>
            <td>${displaySelectedWgs84Coords}</td>
            <td class="text-center">${displaySelectedConfidence}</td>
            <td class="text-center">${displaySelectedApiName}</td>
            <td class="text-center">${displaySelectedActionButtons}</td>
            <td><div class="address-cell-content">${displaySelectedLlmReason}</div></td>
        `;
    });

    // Add 'selected' class to the highlighted row
    if (highlightIndex > -1) {
        const localIndex = highlightIndex - indexOffset;
        if (tbody.children[localIndex]) {
            tbody.children[localIndex].classList.add('selected');
        }
    }
}

/**
 * Clears the map search results table and resets its title to the default state.
 */
export function clearMapSearchResults() {
    const tableBody = document.getElementById('map-search-results-body');
    const titleElement = document.getElementById('poi-results-title');

    if (tableBody) {
        tableBody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">请使用上方搜索框为当前地址查找POI</td></tr>';
    }
    if (titleElement) {
        titleElement.innerHTML = '地图搜索结果';
    }
    // Also clear the global poiResults variable to prevent stale data usage
    if (window.poiResults) {
        window.poiResults = [];
    }
}

/**
 * Renders the map search results in the table.
 * @param {HTMLElement} tableBody - The tbody element to populate.
 * @param {Array} results - The array of POI results.
 * @param {string} originalKeyword - The original search keyword.
 */
export function displayMapSearchResults(tableBody, results, originalKeyword) {
    if (!tableBody) return;

    // console.log("[DEBUG-UI] displayMapSearchResults called.");
    const titleElement = document.getElementById('poi-results-title');
    // console.log("[DEBUG-UI] Found title element:", titleElement);

    // 清空现有结果
    tableBody.innerHTML = '';
    
    if (!Array.isArray(results) || results.length === 0) {
        if (titleElement) {
            titleElement.innerHTML = '地图搜索结果';
        }
        tableBody.innerHTML = '<tr><td colspan="6" class="text-center">未找到相关地点。</td></tr>';
        return;
    }

    // console.log("[DEBUG-UI] First result object:", results[0]);
    if (titleElement && results[0].source_display_name) {
        const sourceName = results[0].source_display_name;
        // console.log("[DEBUG-UI] Source name found:", sourceName);
        titleElement.innerHTML = `地图搜索结果 <small class="text-muted"> - ${sourceName}</small>`;
    } else {
        // console.log("[DEBUG-UI] Source name NOT found or title element missing.");
    }

    // --- 关键修复：移除前端置信度计算 ---
    // 前端不再负责计算置信度，而是直接使用后端提供的值。
    // 如果后端没有提供confidence，则显示'-'
    const processedResults = results.map(poi => {
        return {
            ...poi,
            // 直接使用后端传来的置信度，如果没有则为 undefined
            _confidence: poi.confidence 
        };
    });

    // 根据后端计算的置信度降序排序
    processedResults.sort((a, b) => (b._confidence || 0) - (a._confidence || 0));

    // 为每个结果创建并添加一行
    processedResults.forEach((result, index) => {
        const row = document.createElement('tr');
        // --- BUG FIX ---
        // The original `data-poi-index` was based on the sorted list, which didn't match
        // the original index in the `map-search.js` state. Now, we find the original index.
        const originalIndex = results.indexOf(result);
        row.setAttribute('data-poi-index', originalIndex);

        const confidenceText = typeof result._confidence === 'number' 
            ? `${(result._confidence * 100).toFixed(1)}%`
            : '-';

        // --- BUG FIX ---
        // The button class was hardcoded to `btn-success`. It should be dynamic.
        // However, this function is for initial display, and no item is selected yet.
        // So we default all buttons to the unselected state 'btn-outline-success'.
        const buttonClass = "btn btn-sm btn-outline-success select-poi-btn";

        row.innerHTML = `
            <td class="text-center">${index + 1}</td>
            <td>${result.name || '-'}</td>
            <td>${result.address || '-'}</td>
            <td>${result.pname || ''}${result.cityname || ''}${result.adname || ''}</td>
            <td class="text-center">${confidenceText}</td>
            <td class="text-center">
                <button class="${buttonClass}" title="选择此点">
                    <i class="bi bi-check-lg"></i>
                </button>
            </td>
        `;
        tableBody.appendChild(row);
    });
}
