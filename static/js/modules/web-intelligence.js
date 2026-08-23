import { showToast, checkUserPoints, escapeHtml } from './utils.js';
import { fetchAPI } from './api.js';

// 智能地址情报三步骤模块
class WebIntelligenceManager {
    constructor() {
        this.currentStep = 1;
        this.currentAddress = null;
        this.currentIndex = -1; // 当前地址在结果列表中的索引
        this.dossier = null; // 第一步生成的情报档案
        this.poiCandidates = []; // POI候选列表
        this.keywordSuggestions = []; // 第三步关键词建议
        
        // 地址级别的状态存储
        this.addressStates = new Map();
        
        this.initializeEventListeners();
        this.initializeStepNavigation();
    }

    // 保存当前地址的网络信息状态
    saveAddressWebState(address, index) {
        if (!address) return;
        
        const stateKey = `${address}_${index}`;
        this.addressStates.set(stateKey, {
            currentStep: this.currentStep,
            dossier: this.dossier ? JSON.parse(JSON.stringify(this.dossier)) : null,
            poiCandidates: [...this.poiCandidates],
            keywordSuggestions: [...this.keywordSuggestions],
            timestamp: Date.now()
        });
        
        // console.log(`💾 已保存网络信息状态: ${stateKey}`, this.addressStates.get(stateKey));
    }

    // 恢复地址的网络信息状态
    restoreAddressWebState(address, index) {
        if (!address) return false;
        
        const stateKey = `${address}_${index}`;
        const savedState = this.addressStates.get(stateKey);
        
        // **无论如何，先重置当前UI状态**
        this.resetState();
        
        if (savedState) {
            // console.log(`📥 恢复网络信息状态: ${stateKey}`, savedState);
            
            this.currentStep = savedState.currentStep || 1;
            this.dossier = savedState.dossier ? JSON.parse(JSON.stringify(savedState.dossier)) : null;
            this.poiCandidates = [...savedState.poiCandidates];
            this.keywordSuggestions = [...savedState.keywordSuggestions];
            
            // 恢复UI显示
            if (this.dossier) {
                this.displayStep1Results(this.dossier);
                this.markStepCompleted(1);
            }
            
            if (this.keywordSuggestions.length > 0) {
                this.displayStep3Results(this.keywordSuggestions);
                this.markStepCompleted(3);
            }
            
            this.updateStep3Prerequisites();
            this.updateNavigationButtons();
            
            return true;
        }
        
        // console.log(`📭 未找到网络信息状态: ${stateKey}`);
        return false;
    }

    // 清除地址的网络信息状态
    clearAddressWebState(address, index) {
        if (!address) return;
        
        const stateKey = `${address}_${index}`;
        this.addressStates.delete(stateKey);
        // console.log(`🗑️ 已清除网络信息状态: ${stateKey}`);
    }

    initializeEventListeners() {
        // 地址输入框变更时，实时更新 currentAddress
        const input = document.getElementById('currentAnalysisAddressInput');
        if (input) {
            input.addEventListener('input', (e) => {
                const value = (e.target.value || '').trim();
                this.currentAddress = value || this.currentAddress; // 允许用户清空但不破坏已有状态
            });
        }

        // 第一步：搜集信息按钮
        document.getElementById('step1SearchBtn')?.addEventListener('click', () => {
            this.executeStep1();
        });

        // 第三步：生成关键词建议按钮
        document.getElementById('step3SuggestBtn')?.addEventListener('click', () => {
            this.executeStep3();
        });

        // 步骤控制按钮
        document.getElementById('prevStepBtn')?.addEventListener('click', () => {
            this.goToPreviousStep();
        });

        document.getElementById('nextStepBtn')?.addEventListener('click', () => {
            this.goToNextStep();
        });

        // 步骤导航点击
        document.querySelectorAll('.step-item').forEach(item => {
            item.addEventListener('click', () => {
                const step = parseInt(item.dataset.step);
                if (this.canNavigateToStep(step)) {
                    this.goToStep(step);
                }
            });
        });
    }

    initializeStepNavigation() {
        this.updateStepDisplay();
        this.updateNavigationButtons();
    }

    // 设置当前分析的地址
    setCurrentAddress(address, index = -1) {
        const normalized = (address || '').trim();
        const isSame = normalized && normalized === (this.currentAddress || '').trim();
        
        // 保存当前状态（如果有的话）
        if (this.currentAddress && this.currentIndex >= 0 && !isSame) {
            this.saveAddressWebState(this.currentAddress, this.currentIndex);
        }
        
        this.currentAddress = normalized || null;
        this.currentIndex = index;
        
        const input = document.getElementById('currentAnalysisAddressInput');
        if (input) {
            input.value = normalized || '';
        }
        
        // 恢复或重置状态
        this.restoreAddressWebState(normalized, index);
        this.goToStep(1); // 总是重置到第一步
    }

    // 设置POI候选列表（从POI地图搜索获取）
    setPoiCandidates(candidates) {
        // 兼容：如果传入的是包含 .results 字段的响应，提取其中数组
        if (candidates && Array.isArray(candidates.results)) {
            this.poiCandidates = candidates.results;
        } else {
            this.poiCandidates = Array.isArray(candidates) ? candidates : [];
        }
    }

    // 重置所有状态
    resetState() {
        this.dossier = null;
        this.validationResult = null;
        this.keywordSuggestions = [];
        
        // 清空结果显示
        document.getElementById('step1Results').style.display = 'none';
        document.getElementById('step2Results').style.display = 'none';
        document.getElementById('step3Results').style.display = 'none';
        
        // 重置步骤状态
        document.querySelectorAll('.step-item').forEach(item => {
            item.classList.remove('completed', 'active');
        });
        
        this.updateStep3Prerequisites();
    }

    // 第一步：搜集摘录地址信息
    async executeStep1() {
        if (!checkUserPoints()) return;

        // 以输入框中的最新地址为准
        const input = document.getElementById('currentAnalysisAddressInput');
        if (input && input.value && input.value.trim()) {
            this.currentAddress = input.value.trim();
        }

        if (!this.currentAddress) {
            showToast('请先选择要分析的地址', 'warning');
            return;
        }

        const spinner = document.getElementById('step1Spinner');
        const btn = document.getElementById('step1SearchBtn');
        const resultsDiv = document.getElementById('step1Results');

        try {
            // 显示加载状态
            spinner.style.display = 'block';
            btn.disabled = true;
            resultsDiv.style.display = 'none';

            // 调用后端API
            const data = await fetchAPI('/geocode/web_intelligence/search_collate', {
                method: 'POST',
                body: JSON.stringify({ original_address: this.currentAddress })
            });

            if (data.success) {
                this.dossier = data.dossier;
                this.displayStep1Results(data.dossier);
                this.markStepCompleted(1);
                // 测试需求：完成第一步后即可开放第三步
                this.updateStep3Prerequisites();
                
                // 保存当前状态
                if (this.currentAddress && this.currentIndex >= 0) {
                    this.saveAddressWebState(this.currentAddress, this.currentIndex);
                }
                
                showToast('信息搜集完成', 'success');
            } else {
                throw new Error(data.message || data.error || '搜集信息失败');
            }

        } catch (error) {
            console.error('第一步执行失败:', error);
            showToast('搜集信息失败: ' + error.message, 'error');
        } finally {
            spinner.style.display = 'none';
            btn.disabled = false;
        }
    }

    // 显示第一步结果
    displayStep1Results(dossier) {
        const excerptsList = document.getElementById('step1ExcerptsList');
        const resultsDiv = document.getElementById('step1Results');

        if (!dossier.collated_excerpts || dossier.collated_excerpts.length === 0) {
            excerptsList.innerHTML = '<div class="alert alert-info">未搜集到相关地址信息</div>';
        } else {
            excerptsList.innerHTML = dossier.collated_excerpts.map((excerpt) => `
                <div class="list-group-item excerpt-item p-2 mb-2">
                    <div class="mb-0">${escapeHtml(excerpt.excerpt)}</div>
                </div>
            `).join('');
        }

        resultsDiv.style.display = 'block';
    }

    // 第三步：生成关键词建议
    async executeStep3() {
        if (!checkUserPoints()) return;

        // 若尚未完成信息搜集，则自动执行第一步后再生成关键词
        if (!this.dossier) {
            try {
                await this.executeStep1();
            } catch (e) {
                // 忽略，后续会判断dossier是否存在
            }
            if (!this.dossier) {
                showToast('信息搜集失败，无法生成关键词建议', 'error');
                return;
            }
        }

        // 无论第二步是否匹配都允许生成关键词

        const spinner = document.getElementById('step3Spinner');
        const btn = document.getElementById('step3SuggestBtn');
        const resultsDiv = document.getElementById('step3Results');

        try {
            // 显示加载状态
            spinner.style.display = 'block';
            btn.disabled = true;
            resultsDiv.style.display = 'none';

            // 调用后端API
            // 以输入框中的最新地址为准
            const input = document.getElementById('currentAnalysisAddressInput');
            if (input && input.value && input.value.trim()) {
                this.currentAddress = input.value.trim();
            }

            const data = await fetchAPI('/geocode/web_intelligence/suggest_keywords', {
                method: 'POST',
                body: JSON.stringify({
                    original_address: this.currentAddress,
                    poi_candidates: this.poiCandidates,
                    dossier: this.dossier,
                    mismatch_reasons: (this.validationResult && this.validationResult.mismatch_reasons) ? this.validationResult.mismatch_reasons : []
                })
            });

            if (data.success) {
                this.keywordSuggestions = data.keyword_suggestions;
                this.displayStep3Results(data.keyword_suggestions);
                this.markStepCompleted(3);
                
                // 保存当前状态
                if (this.currentAddress && this.currentIndex >= 0) {
                    this.saveAddressWebState(this.currentAddress, this.currentIndex);
                }
                
                showToast('关键词建议生成完成', 'success');
            } else {
                throw new Error(data.error || '生成关键词建议失败');
            }

        } catch (error) {
            console.error('第三步执行失败:', error);
            showToast('生成关键词建议失败: ' + error.message, 'error');
        } finally {
            spinner.style.display = 'none';
            btn.disabled = false;
        }
    }

    // 显示第三步结果
    displayStep3Results(suggestions) {
        const keywordsList = document.getElementById('step3KeywordsList');
        const resultsDiv = document.getElementById('step3Results');

        if (!suggestions || suggestions.length === 0) {
            keywordsList.innerHTML = '<div class="alert alert-info">未生成关键词建议</div>';
        } else {
            keywordsList.innerHTML = suggestions.map((suggestion, index) => {
                return `
                <div class="keyword-suggestion d-flex justify-content-between align-items-center p-3 mb-2 rounded">
                    <div class="keyword-info flex-grow-1 me-3">
                        <strong class="text-dark d-block">${escapeHtml(suggestion.display)}</strong>
                        <p class="small mb-0 text-muted">${escapeHtml(suggestion.reason)}</p>
                    </div>
                    <div class="keyword-action">
                        <button class="btn btn-sm btn-outline-primary use-keyword-btn" type="button">
                            <i class="bi bi-search"></i> 使用搜索
                        </button>
                    </div>
                </div>
                `;
            }).join('');
            keywordsList.querySelectorAll('.use-keyword-btn').forEach((button, index) => {
                button.addEventListener('click', () => this.useKeywordForSearch(suggestions[index].query));
            });
        }

        resultsDiv.style.display = 'block';
    }

    // 使用关键词进行搜索
    useKeywordForSearch(keyword) {
        // 将关键词填入POI搜索框并触发搜索
        const mapSearchInput = document.getElementById('mapSearchInput');
        if (mapSearchInput) {
            mapSearchInput.value = keyword;
            
            // 全局通知：本次是“建议关键词触发的POI搜索”，需对当前记录锁定搜索框
            // 解决问题：防止POI选点后，校准面板的地址自动回填覆盖搜索关键词
            try {
                window.isPoiSearchLocked = true;
            } catch (e) { console.warn(e); }
            
            // 触发搜索按钮点击
            document.getElementById('mapSearchBtn')?.click();
            // 切换到POI搜索标签
            document.getElementById('poi-search-tab')?.click();
            showToast(`已使用关键词"${keyword}"进行搜索`, 'info');
        }
    }

    // 在POI搜索结果中高亮选中的POI
    highlightSelectedPOI(index) {
        // 这个方法需要与POI搜索模块集成
        // 暂时只显示提示
        showToast(`建议选择POI搜索结果中的第${index + 1}项`, 'info');
    }

    // 步骤导航相关方法
    goToStep(step) {
        if (!this.canNavigateToStep(step)) {
            return;
        }

        this.currentStep = step;
        this.updateStepDisplay();
        this.updateNavigationButtons();
    }

    goToPreviousStep() {
        if (this.currentStep > 1) {
            this.goToStep(this.currentStep - 1);
        }
    }

    goToNextStep() {
        if (this.currentStep < 3) {
            this.goToStep(this.currentStep + 1);
        }
    }

    canNavigateToStep(step) {
        // 可以导航到当前步骤或之前已完成的步骤
        return step <= this.currentStep || this.isStepCompleted(step - 1);
    }

    isStepCompleted(step) {
        const stepItem = document.querySelector(`.step-item[data-step="${step}"]`);
        return stepItem?.classList.contains('completed');
    }

    markStepCompleted(step) {
        const stepItem = document.querySelector(`.step-item[data-step="${step}"]`);
        if (stepItem) {
            stepItem.classList.add('completed');
        }
    }

    updateStepDisplay() {
        // 隐藏所有步骤内容
        document.querySelectorAll('.step-content').forEach(content => {
            content.style.display = 'none';
        });

        // 显示当前步骤内容
        const currentContent = document.getElementById(`step${this.currentStep}-content`);
        if (currentContent) {
            currentContent.style.display = 'block';
        }

        // 更新步骤导航状态
        document.querySelectorAll('.step-item').forEach(item => {
            const step = parseInt(item.dataset.step);
            item.classList.remove('active');
            if (step === this.currentStep) {
                item.classList.add('active');
            }
        });
    }

    updateNavigationButtons() {
        const prevBtn = document.getElementById('prevStepBtn');
        const nextBtn = document.getElementById('nextStepBtn');

        if (prevBtn) {
            prevBtn.disabled = this.currentStep === 1;
        }

        if (nextBtn) {
            nextBtn.disabled = this.currentStep === 3;
            nextBtn.textContent = this.currentStep === 3 ? '完成' : '下一步';
        }
    }

    updateStep3Prerequisites() {
        const prerequisitesDiv = document.getElementById('step3Prerequisites');
        const suggestBtn = document.getElementById('step3SuggestBtn');
        
        const hasStep1 = this.dossier !== null;
        if (hasStep1) {
            prerequisitesDiv.className = 'alert alert-success';
            prerequisitesDiv.innerHTML = '<i class="bi bi-check-circle"></i> 已可生成关键词建议';
        } else {
            prerequisitesDiv.className = 'alert alert-info';
            prerequisitesDiv.innerHTML = '<i class="bi bi-info-circle"></i> 点击“生成关键词建议”将自动完成信息搜集后再生成建议';
        }
        if (suggestBtn) suggestBtn.disabled = false; // 始终允许点击，内部自动补全第一步
    }

    // 获取所有地址状态数据（供任务保存使用）
    getAddressStates() {
        return Object.fromEntries(this.addressStates);
    }

    // 恢复地址状态数据（从任务恢复时使用）
    restoreAddressStates(states) {
        if (states && typeof states === 'object') {
            this.addressStates = new Map(Object.entries(states));
            // console.log('📥 已恢复网络信息地址状态', this.addressStates);
        }
    }
}

// 创建全局实例
const webIntelligence = new WebIntelligenceManager();

// 导出供其他模块使用
export { webIntelligence };
