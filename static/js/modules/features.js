import { createAndAppendElement, showToast } from './utils.js';
import { saveLocationTypeToServer } from './api.js';
import { showLoading, hideLoading } from './utils.js';
import { performSmartSearch } from './api.js';
// 移除直接导入，改为通过window对象访问，避免循环依赖
// import { webIntelligence } from './web-intelligence.js';

let locationTypeTags = new Set();
let locationTypeHistory = new Set();

// Internal state for this module
let _currentUser = null;

// 当前正在分析的地址（用于智能地址情报）
let currentAnalysisAddress = null;

// --- Address Cleaning ---

export function cleanAddressText(text) {
    if (typeof text !== 'string') return '';
    return text.split(/\r?\n|\r/)
        .map(line => line.trim().replace(/^\d+[\.\s、]+/, '').replace(/　/g, '').replace(/\s+/g, ' ').trim())
        .filter(line => line)
        .join('\n');
}

// --- Location Type Tags ---

function updateLocationTypeTagsDisplay() {
    const tagsContainer = document.getElementById('locationTypeTags');
    if (!tagsContainer) return;
    tagsContainer.innerHTML = '';
    locationTypeTags.forEach(tag => {
        createAndAppendElement('div', {
            className: 'location-type-tag',
            innerHTML: `${tag}<span class="remove-tag" data-tag="${tag}">&times;</span>`,
            parent: tagsContainer
        });
    });
}

function addLocationTypeTag(tag) {
    tag = tag.trim();
    if (tag && !locationTypeTags.has(tag)) {
        locationTypeTags.add(tag);
        updateLocationTypeTagsDisplay();
        saveLocationTypeToServer(tag).then(data => {
            if (data.success) {
                locationTypeHistory.add(tag);
            }
        });
    }
}

function removeLocationTypeTag(tag) {
    locationTypeTags.delete(tag);
    updateLocationTypeTagsDisplay();
}

function handleLocationTypeInput(value) {
    const tags = value.split(/[,，、]/).map(tag => tag.trim()).filter(tag => tag);
    tags.forEach(addLocationTypeTag);
    const locationTypeInput = document.getElementById('locationType');
    if (locationTypeInput) locationTypeInput.value = '';
}

// --- Main Initializer for Features ---

export function initializeFeatures(currentUser) {
    _currentUser = currentUser; // Store the current user for later use

    // Event delegation for removing location type tags
    const tagsContainer = document.getElementById('locationTypeTags');
    if (tagsContainer) {
        tagsContainer.addEventListener('click', (event) => {
            if (event.target.classList.contains('remove-tag')) {
                const tagToRemove = event.target.dataset.tag;
                if (tagToRemove) {
                    removeLocationTypeTag(tagToRemove);
                }
            }
        });
    }

    // Listener for location type input
    const locationTypeInput = document.getElementById('locationType');
    if(locationTypeInput) {
        locationTypeInput.addEventListener('change', (event) => {
            handleLocationTypeInput(event.target.value);
        });
    }

    // Add other feature initializations here...
    const searchForm = document.getElementById('smartSearchForm');
    if (searchForm) {
        searchForm.addEventListener('submit', handleSmartSearch);
    }
}

function displaySmartSearchResults(results) {
    const tableBody = document.querySelector('#searchResultsTable tbody');
    if (!tableBody) return;
    tableBody.innerHTML = ''; // Clear previous results

    if (!results || results.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="3" class="text-center">未找到相关地点信息。</td></tr>';
        return;
    }

    results.forEach((item, index) => {
        const row = `
            <tr>
                <td>${index + 1}</td>
                <td>
                    <div class="location-name">${item.name || '未知名称'}</div>
                    <div class="location-tags">
                        <span class="location-tag">${item.type || '未知类型'}</span>
                        <span class="location-tag">${item.source || '未知来源'}</span>
                    </div>
                </td>
                <td>
                    <div class="relation-info">${item.address || '无地址信息'}</div>
                </td>
            </tr>`;
        tableBody.insertAdjacentHTML('beforeend', row);
    });
}

export async function handleSmartSearch(event) {
    event.preventDefault();
    const searchInput = document.getElementById('searchInput');
    const searchTerm = searchInput.value.trim();
    if (!searchTerm) {
        showToast('请输入搜索关键词', 'warning');
        return;
    }

    const mode = document.querySelector('input[name="smartSearchMode"]:checked').value;

    // 新策略：前端不再进行积分预检查

    const spinner = document.getElementById('searchSpinner');
    spinner.style.display = 'block';
    
    // Also show the results wrapper
    const resultsWrapper = document.getElementById('searchResultsWrapper');
    resultsWrapper.style.display = 'block';

    try {
        const data = await performSmartSearch(searchTerm, mode);
        displaySmartSearchResults(data.results);
    } catch (error) {
        showToast(error.message, 'error');
        console.error('智能搜索失败:', error);
    } finally {
        spinner.style.display = 'none';
    }
}

// === 智能地址情报相关函数 ===

/**
 * 设置智能地址情报的当前分析地址
 * @param {string} address - 要分析的地址
 */
export function setWebIntelligenceAddress(address, index = -1) {
    currentAnalysisAddress = address;
    // 通过window对象访问，避免循环依赖
    if (window.webIntelligence) {
        window.webIntelligence.setCurrentAddress(address, index);
    }
}

/**
 * 设置智能地址情报的POI候选列表
 * @param {Array} candidates - POI候选列表
 */
export function setWebIntelligencePOICandidates(candidates) {
    // 通过window对象访问，避免循环依赖
    if (window.webIntelligence) {
        window.webIntelligence.setPoiCandidates(candidates);
    }
}

/**
 * 获取当前分析地址
 * @returns {string|null} 当前分析地址
 */
export function getCurrentAnalysisAddress() {
    return currentAnalysisAddress;
}