import { geocodeAddresses, autoSelectPoint, fetchAPI } from './api.js';
import { ENDPOINTS, SELECTORS } from './constants.js';
import { showToast } from './utils.js';
import { displayCascadeResults } from './ui.js'; // This will be moved to results-table.js later
import { updateResultsOverviewMapMarkers, ensureResultsOverviewMap } from './map.js';
import { cleanAddresses } from './address-cleaner.js';

/**
 * Handles the main geocoding process.
 * @param {object} addressInputModule - The initialized address input module.
 * @param {object} resultsOverviewMap - The Leaflet map instance for the overview.
 * @param {boolean} isSmartMode - Whether the geocoding is in smart mode.
 * @returns {object|null} An object containing currentResults and selectedResults, or null on failure.
 */
export async function handleGeocodeClick(addressInputModule, resultsOverviewMap, options = {}) {
    if (!addressInputModule) {
        console.error("Address input module is not initialized.");
        return null;
    }

    // 第三层保障：在开始处理前，强制执行一次最终的地址清洗
    const addressesTextarea = document.getElementById('addresses');
    if (addressesTextarea) {
        const originalValue = addressesTextarea.value;
        const cleanedValue = cleanAddresses(originalValue);
        if (originalValue !== cleanedValue) {
            addressesTextarea.value = cleanedValue;
            // 触发input事件以更新地址计数等UI
            addressesTextarea.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
        }
    }

    const addresses = addressInputModule.getAddresses();
    const locationTags = addressInputModule.getLocationTypeTags();
    
    if (addresses.length === 0) {
        showToast('请输入至少一个地址', 'warning');
        return null;
    }

    try {
        /* console.log('开始地理编码处理:', {
            addresses,
            isSmartMode,
            locationTags
        }); */

        // 异步记录使用过的后缀，这是一个"即发即忘"的请求，不阻塞主流程
        if (locationTags.length > 0) {
            fetchAPI(ENDPOINTS.recordUsedSuffixes, {
                method: 'POST',
                body: JSON.stringify({ suffixes: locationTags })
            }).catch(error => {
                // 在后台默默记录错误，不打扰用户
                console.error('记录使用过的后缀时出错:', error);
            });
        }

        // 显示批量结果容器和加载遮罩
        const cascadeContainer = document.querySelector(SELECTORS.resultsContainer);
        // console.log('🎯 查找结果容器:', cascadeContainer);
        if (cascadeContainer) {
            cascadeContainer.style.display = 'block';
            // console.log('✅ 结果容器已显示');
            // 确保容器布局稳定，再初始化/校准地图
            await new Promise(r => setTimeout(r, 120));
        } else {
            console.error('❌ 未找到结果容器 #cascadeResultsContainer');
        }
        
        // 使用全局加载遮罩由 geocodeAddresses 内部控制
        
        try {
            const runMode = options.run_mode === 'smart' ? 'smart' : 'multisource';
            const data = await geocodeAddresses(
                addresses,
                runMode === 'smart' ? 'smart' : 'default',
                locationTags,
                options,
            );
            
            if (!data || !data.results) {
                console.error('地理编码结果无效:', data);
                showToast('获取地理编码结果失败', 'error');
                return null;
            }
        
        // 处理批量语义预分析结果
        if (data.semantic_analysis && data.semantic_analysis.theme_name) {
            try {
                const themeName = data.semantic_analysis.theme_name;
                
                // 更新表头显示的任务名称
                const taskNameDisplay = document.getElementById('taskNameDisplay');
                if (taskNameDisplay && themeName !== '地理编码任务') {
                    taskNameDisplay.textContent = themeName;
                    // console.log('已自动设置任务名称:', themeName);
                }
                
                
                
                // 兼容性：也更新旧的显示元素（如果存在）
                const displayNameElement = document.getElementById('locationNameDisplay');
                if (displayNameElement) {
                    displayNameElement.textContent = themeName;
                }
                
                if (data.semantic_analysis.enhanced) {
                    showToast(`智能分析完成，建议任务名称：${themeName}`, 'success');
                } else if (data.semantic_analysis.error) {
                    console.warn('语义分析警告:', data.semantic_analysis.error);
                }
            } catch (e) {
                console.error('处理语义分析结果时出错:', e);
            }
        }

        // 修复：确保每个结果都带有api_results字段
        const currentResults = data.results.map((r, index) => ({
            ...r,
            tracking_address_index: index,
            api_results: Array.isArray(r.api_results) ? r.api_results : []
        }));
        const selectedResults = getSelectedResults(currentResults);
        
        // 同步到全局，供“逐条查看与校准”等功能使用
        try {
            window.currentResults = currentResults;
            window.selectedResults = selectedResults;
            window.currentGeocodingTracking = data.tracking || null;
        } catch (e) {
            // 忽略在严格模式或非浏览器环境下的赋值异常
        }
        
        // 加载遮罩已在 geocodeAddresses 中隐藏
        
        // 更新结果表格
        const cascadeTableBody = document.getElementById('cascadeResultsBody');
        /* console.log('🎯 查找结果表格:', cascadeTableBody);
        console.log('🎯 结果数据:', currentResults);
        console.log('🎯 结果数据长度:', currentResults.length); */
        
        if (cascadeTableBody) {
            // console.log('✅ 开始显示结果到表格...');
            if (typeof window.updateResultsTable === 'function') {
                window.updateResultsTable(currentResults, { scroll: true });
            } else {
                displayCascadeResults(cascadeTableBody, currentResults);
            }
            // console.log('✅ 结果表格已更新');
        } else {
            console.error('❌ 未找到结果表格 #cascadeResultsBody');
        }
        
        // 更新地图标记（确保地图可用）
        const ensuredMap = resultsOverviewMap || ensureResultsOverviewMap('map');
        if (ensuredMap) {
            // console.log('🗺️ 更新地图标记...');
            updateResultsOverviewMapMarkers(ensuredMap, selectedResults);
            // console.log('✅ 地图标记已更新');
            try { window.resultsOverviewMap = ensuredMap; } catch (e) {}
        } else {
            console.log('⚠️ 总览地图未提供，跳过地图更新');
        }

        // 重新获取容器以确保滚动
        const finalCascadeContainer = document.querySelector(SELECTORS.resultsContainer);
        // console.log('🎯 滚动目标容器:', finalCascadeContainer);
        
        // 滚动到结果区域
        if (finalCascadeContainer) {
            // console.log('📜 开始滚动到结果区域...');
            finalCascadeContainer.scrollIntoView({ behavior: 'smooth' });
            // console.log('✅ 滚动完成');
        } else {
            console.error('❌ 滚动失败：未找到结果容器');
        }
        
        // 若校准面板已打开，则自动刷新当前显示或载入第一条，保证“第一时间更新”
        try {
            const detailedSection = document.getElementById('detailedReviewSection');
            const isCalibrationOpen = detailedSection && detailedSection.style.display !== 'none';
            if (isCalibrationOpen && window.calibrationPanel && Array.isArray(window.currentResults) && window.currentResults.length > 0) {
                const currentIndex = window.calibrationPanel.isShowingResult 
                    ? window.currentResults.findIndex((_, i) => window.calibrationPanel.isShowingResult(i)) 
                    : 0;
                const indexToShow = currentIndex >= 0 ? currentIndex : 0;
                window.calibrationPanel.showPanelFor(window.currentResults[indexToShow], indexToShow, window.currentResults.length);
            }
        } catch (e) {
            console.warn('刷新校准面板时出现非致命错误:', e);
        }
        
        return { currentResults, selectedResults };
        
        } catch (error) {
            console.error('地理编码处理出错:', error);
            // 检查Key失效相关错误
            if (typeof error.message === 'string') {
            if (error.message.includes('Key无效') || error.message.includes('Key失效')) {
                showToast('API Key已失效，请重新填写并保存', 'error');
                // 自动打开设置模态框并聚焦对应Key输入框
                const settingsModal = new bootstrap.Modal(document.getElementById('settingsModal'));
                settingsModal.show();
                // 尝试聚焦Key输入框
                setTimeout(() => {
                    if (error.message.includes('高德')) {
                        document.getElementById('settingsAmapKey')?.focus();
                    } else if (error.message.includes('百度')) {
                        document.getElementById('settingsBaiduKey')?.focus();
                    } else if (error.message.includes('天地图')) {
                        document.getElementById('settingsTiandituKey')?.focus();
                    }
                }, 500);
                return null;
            }
            if (error.message.includes('Key已超限')) {
                showToast('API Key已超出配额，请更换Key或稍后再试', 'warning');
                return null;
            }
        }
        showToast(error.message || '地理编码过程中发生错误', 'error');
        return null;
    }
}
catch (outerError) {
    console.error('地理编码初始化阶段出错:', outerError);
    showToast(outerError.message || '地理编码过程中发生错误', 'error');
    return null;
}
}

function getSelectedResults(currentResults) {
    if (!currentResults || !Array.isArray(currentResults)) return [];
    
    return currentResults.filter(item => item.selected_result);
}

/**
 * Handles the auto-selection of a POI using the LLM service.
 */
export async function handleAutoSelect() {
    const originalAddress = document.getElementById('address-input').value;
    const sourceContext = '地图搜索';
    
    // poiResults is expected to be a global variable holding the results from poi_search
    if (typeof poiResults === 'undefined' || !Array.isArray(poiResults)) {
        console.error('poiResults is not available.');
        showToast('POI结果列表不存在，无法进行智能选点。', 'error');
        return;
    }

    if (!originalAddress || poiResults.length === 0) {
        showToast('请输入地址并先进行POI搜索。', 'warning');
        return;
    }

    try {
        const response = await autoSelectPoint(poiResults, originalAddress, sourceContext);
        
        if (response.error) {
            const reasonText = response.reasons && response.reasons.length > 0 
                ? `理由: ${response.reasons[0]}` 
                : '无具体理由。';
            console.warn('LLM auto-select failed:', response.error, 'Reasons:', response.reasons);
            
            if (response.error === 'NO_HIGH_CONFIDENCE' || response.error === 'NEED_WEB_INFO') {
                showToast(`AI未能自动确定最佳匹配项。${reasonText}`, 'info');
            } else {
                showToast(`智能选点失败: ${response.error}`, 'error');
            }
            return;
        }

        if (response && typeof response.selected_index === 'number' && response.selected_index !== -1) {
            const selectedPoi = poiResults[response.selected_index];
            if (selectedPoi) {
                const reasonText = response.llm_reason || '高置信度匹配';
                // console.log('LLM auto-selected POI:', selectedPoi, 'Reason:', reasonText);
                
                // This function needs to exist in your UI logic to highlight the result
                if (typeof selectAndHighlightPoi === 'function') {
                    selectAndHighlightPoi(response.selected_index);
                } else {
                    console.warn('Function selectAndHighlightPoi is not defined, cannot highlight result.');
                }
                
                showToast(`智能选点成功。理由: ${reasonText}`, 'success');
            } else {
                console.error('LLM returned a valid index but POI was not found in the original list.');
                showToast('智能选点返回索引无效。', 'error');
            }
        } else {
            // console.log('LLM did not return a valid selection or error.');
            showToast('智能选点未返回明确结果。', 'warning');
        }
    } catch (error) {
        console.error('An error occurred during the auto-selection process:', error);
        showToast('智能选点服务异常。', 'error');
    }
}

// 局部加载遮罩逻辑已移除，统一使用全局加载遮罩
