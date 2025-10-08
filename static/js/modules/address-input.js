import { createAndAppendElement, showToast } from './utils.js';
import { fetchAPI } from './api.js';

// --- State for this module ---
let locationTypeTags = new Set();
let locationTypeHistory = new Set(); // To be populated from server later if needed

// --- DOM Elements ---
const addressesTextarea = document.getElementById('addresses');
const locationTypeInput = document.getElementById('locationType');
const tagsContainer = document.getElementById('locationTypeTags');
const autoCompleteBtn = document.getElementById('autoCompleteBtn');
const autoSplitBtn = document.getElementById('autoSplitBtn');
const splitDelimitersInput = document.getElementById('splitDelimiters');
const prependRegionInput = document.getElementById('prependRegionInput');
const prependRegionBtn = document.getElementById('prependRegionBtn');
const cleanAddressesBtn = document.getElementById('cleanAddressesBtn');
const clearLocationTypeBtn = document.getElementById('clearLocationType');
const addressCountDisplay = document.getElementById('addressCountDisplay');
const tagsWrapper = document.getElementById('locationTypeTagsWrapper');


function updateLocationTypeTagsDisplay() {
    if (!tagsContainer || !tagsWrapper) return;

    // 根据是否有标签来决定是否显示整个包装器
    if (locationTypeTags.size > 0) {
        tagsWrapper.style.display = 'flex'; // 使用flex来保持对齐
    } else {
        tagsWrapper.style.display = 'none';
    }
    
    tagsContainer.innerHTML = '';
    locationTypeTags.forEach(tag => {
        const tagElement = document.createElement('div');
        tagElement.className = 'location-type-tag';
        tagElement.innerHTML = `${tag}<span class="remove-tag">&times;</span>`;
        
        // 添加删除事件监听器
        tagElement.querySelector('.remove-tag').addEventListener('click', () => {
            removeLocationTypeTag(tag);
        });
        
        tagsContainer.appendChild(tagElement);
    });
}

function addLocationTypeTag(tag) {
    tag = tag.trim();
    if (tag && !locationTypeTags.has(tag)) {
        locationTypeTags.add(tag);
        updateLocationTypeTagsDisplay();
    }
}

function removeLocationTypeTag(tag) {
    locationTypeTags.delete(tag);
    updateLocationTypeTagsDisplay();
    showToast(`地名类型 "${tag}" 已移除`, 'info');
}

function handleLocationTypeInput(value) {
    const tags = value.split(/[,，、]/).map(tag => tag.trim()).filter(tag => tag);
    tags.forEach(addLocationTypeTag);
    if (locationTypeInput) locationTypeInput.value = '';
}

function updateAddressCountDisplay() {
    if (addressesTextarea && addressCountDisplay) {
        const addresses = addressesTextarea.value.trim().split(/\r?\n|\r/).filter(addr => addr.trim());
        addressCountDisplay.textContent = `${addresses.length} 条地址`;
    }
}

function prependRegionToAddresses() {
    if (!addressesTextarea) return;
    const prefix = prependRegionInput ? prependRegionInput.value.trim() : '';
    if (!prefix) {
        showToast('请先输入要前置的省市前缀', 'warning');
        return;
    }

    const lines = addressesTextarea.value.split(/\r?\n|\r/);
    if (lines.length === 0 || lines.every(l => !l.trim())) {
        showToast('请先输入地址内容', 'warning');
        return;
    }

    const updated = lines.map(line => {
        const trimmed = line.trim();
        if (!trimmed) return '';
        // 若该行已以相同前缀开头，则不重复添加
        if (trimmed.startsWith(prefix)) return trimmed;
        return prefix + trimmed;
    }).filter(l => l !== '');

    addressesTextarea.value = updated.join('\n');
    updateAddressCountDisplay();
    showToast('已将前缀添加到每条地址前', 'success');
}

async function autoCompleteAddresses() {
    if (!addressesTextarea) return;
    const addresses = addressesTextarea.value.trim().split('\n').filter(addr => addr.trim());
    if (addresses.length === 0) { 
        showToast('请输入至少一个地址进行补全', 'warning');
        return; 
    }

    const statusDiv = document.getElementById('autoCompleteStatus');
    const progressBar = statusDiv ? statusDiv.querySelector('.progress-bar') : null;
    const processingSpan = document.getElementById('processingAddress');
    
    if (statusDiv) statusDiv.style.display = 'block';
    if (autoCompleteBtn) autoCompleteBtn.disabled = true;
    if (progressBar) progressBar.style.width = '0%';
    if (processingSpan) processingSpan.textContent = '准备开始...';
    
    try {
        if (processingSpan) processingSpan.textContent = `正在发送 ${addresses.length} 个地址...`;
        
        const data = await fetchAPI('/jionlp_autocomplete', {
            method: 'POST',
            body: JSON.stringify({ addresses: addresses })
        });

        if (data && data.completed_addresses && Array.isArray(data.completed_addresses)) {
            addressesTextarea.value = data.completed_addresses.join('\n');
            updateAddressCountDisplay();
            if (processingSpan) processingSpan.textContent = '补全完成！';
            if (progressBar) progressBar.style.width = '100%';
        } else {
            throw new Error('后端返回的数据格式不正确');
        }

    } catch (error) {
        console.error('自动补全过程出错:', error);
        showToast('地址补全处理过程中出现错误: ' + error.message, 'error');
        if (processingSpan) processingSpan.textContent = '补全失败';
    } finally {
        setTimeout(() => {
            if (statusDiv) statusDiv.style.display = 'none';
        }, 2000);
        if (autoCompleteBtn) autoCompleteBtn.disabled = false;
    }
}

function autoSplitAddresses() {
    if (!addressesTextarea) return;
    
    const content = addressesTextarea.value.trim();
    if (!content) {
        showToast('请先输入地址内容', 'warning');
        return;
    }
    
    // 获取分隔符，默认使用中文逗号、英文逗号、顿号和分号
    const delimiters = splitDelimitersInput ? splitDelimitersInput.value.trim() : '，,、;';
    const delimiterArray = delimiters.split(/[,，]/).map(d => d.trim()).filter(d => d);
    
    if (delimiterArray.length === 0) {
        showToast('请至少设置一个分隔符', 'warning');
        return;
    }
    
    try {
        // 构建正则表达式，转义特殊字符
        const escapedDelimiters = delimiterArray.map(d => {
            // 转义正则表达式中的特殊字符
            return d.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        });
        const regex = new RegExp(`[${escapedDelimiters.join('')}]`, 'g');
        
        // 按分隔符分割内容
        const lines = content.split(regex)
            .map(line => line.trim())
            .filter(line => line.length > 0);
        
        if (lines.length === 0) {
            showToast('未找到可分割的内容', 'warning');
            return;
        }
        
        // 更新地址输入框
        addressesTextarea.value = lines.join('\n');
        updateAddressCountDisplay();
        
        showToast(`已按分隔符分行，共生成 ${lines.length} 条地址`, 'success');
        
    } catch (error) {
        console.error('自动分行出错:', error);
        showToast('自动分行过程中出现错误: ' + error.message, 'error');
    }
}

export function initializeAddressInput() {
    // console.log('🔄 初始化地址输入模块开始...');
    
    // console.log('🔍 查找DOM元素...');
    // console.log('  locationTypeInput:', locationTypeInput);
    // console.log('  autoCompleteBtn:', autoCompleteBtn);
    // console.log('  autoSplitBtn:', autoSplitBtn);
    // console.log('  clearLocationTypeBtn:', clearLocationTypeBtn);
    // console.log('  addressesTextarea:', addressesTextarea);
    
    if (locationTypeInput) {
        // console.log('✅ 添加地名类型输入框事件监听器');
        locationTypeInput.addEventListener('change', (e) => handleLocationTypeInput(e.target.value));
        locationTypeInput.addEventListener('blur', (e) => {
             if(e.target.value) handleLocationTypeInput(e.target.value);
        });
    } else {
        console.warn('⚠️ 未找到地名类型输入框元素');
    }
    
    if (clearLocationTypeBtn) {
        // console.log('✅ 添加清空地名类型按钮事件监听器');
        clearLocationTypeBtn.addEventListener('click', () => {
            locationTypeTags.clear();
            updateLocationTypeTagsDisplay();
            showToast('地名类型已清空', 'info');
        });
    } else {
        console.warn('⚠️ 未找到清空地名类型按钮');
    }

    if(autoCompleteBtn) {
        // console.log('✅ 添加自动补全按钮事件监听器');
        autoCompleteBtn.addEventListener('click', autoCompleteAddresses);
    } else {
        console.warn('⚠️ 未找到自动补全按钮元素 #autoCompleteBtn');
    }

    if(autoSplitBtn) {
        // console.log('✅ 添加自动分行按钮事件监听器');
        autoSplitBtn.addEventListener('click', autoSplitAddresses);
    } else {
        console.warn('⚠️ 未找到自动分行按钮元素 #autoSplitBtn');
    }

    if (prependRegionBtn) {
        prependRegionBtn.addEventListener('click', prependRegionToAddresses);
    } else {
        console.warn('⚠️ 未找到统一前缀按钮元素 #prependRegionBtn');
    }

    if (addressesTextarea) {
        // console.log('✅ 添加地址计数更新监听器');
        addressesTextarea.addEventListener('input', updateAddressCountDisplay);
        updateAddressCountDisplay();
    } else {
        console.warn('⚠️ 未找到地址输入框元素，无法添加计数更新监听器');
    }

    // 监听其他模块添加的标签事件
    // console.log('✅ 添加地名类型标签事件监听器');
    document.addEventListener('locationTypeTagAdded', (event) => {
        // console.log('🏷️ 收到标签添加事件:', event.detail.tag);
        const tag = event.detail.tag;
        if (tag && !locationTypeTags.has(tag)) {
            locationTypeTags.add(tag);
            updateLocationTypeTagsDisplay();
        }
    });

    // console.log('✅ 地址输入模块初始化完成');

    // Return a function to get the current state if needed by other modules
    return {
        getAddresses: () => addressesTextarea ? addressesTextarea.value.trim().split(/\r?\n|\r/).map(addr => addr.trim()).filter(addr => addr) : [],
        getLocationTypeTags: () => Array.from(locationTypeTags),
        autoCompleteAddresses: autoCompleteAddresses
    };
} 