import { fetchAPI } from './modules/api.js';
import { escapeHtml } from './modules/utils.js';
import { trackInteraction } from './modules/analytics.js';

// console.log("task_manager.js script loaded.");

// =================================================
// "我的任务"功能模块
// =================================================
export function initializeTaskManager() {
    // console.log("Initializing task manager...");

    // --- 变量和元素定义 ---
    let currentLoadedTask = null; // 存储当前加载的任务信息 {id, name}
    const saveTaskBtn = document.getElementById('saveResultsBtn'); 
    const myTasksBtn = document.getElementById('my-tasks-btn');
    // 我的任务分页状态（模块级）
    let __myTasksPage = 1;
    let __myTasksPerPage = 10;
    
    // 尝试获取模态框，如果不存在则稍后重试
    let saveTaskModalEl = document.getElementById('saveTaskModal');
    let myTasksModalEl = document.getElementById('myTasksModal');
    
    // 如果模态框不存在，稍后重试
    if (!saveTaskModalEl || !myTasksModalEl) {
        // console.log("模态框初始检查失败，开始调试...");
        // console.log("Document ready state:", document.readyState);
        // console.log("Body children count:", document.body.children.length);
        
        // 尝试查找所有的模态框
        const allModals = document.querySelectorAll('.modal');
        // console.log("找到的所有模态框:", allModals.length, Array.from(allModals).map(m => m.id));
        
        // 尝试查找具体的ID
        const saveModal = document.querySelector('#saveTaskModal');
        const tasksModal = document.querySelector('#myTasksModal');
        // console.log("querySelector结果:", { saveModal, tasksModal });
        
        setTimeout(() => {
            saveTaskModalEl = document.getElementById('saveTaskModal');
            myTasksModalEl = document.getElementById('myTasksModal');
            // console.log("500ms后重试结果:", { saveTaskModalEl, myTasksModalEl });
            
            // 再次查找所有模态框
            const retriedAllModals = document.querySelectorAll('.modal');
            // console.log("重试后找到的所有模态框:", retriedAllModals.length, Array.from(retriedAllModals).map(m => m.id));
        }, 500);
    }

    /*
    console.log("Element Handles:", {
        saveTaskBtn,
        myTasksBtn,
        saveTaskModalEl,
        myTasksModalEl
    });
    */
    
    // 检查按钮是否存在
    if (!myTasksBtn) {
        console.error('我的任务按钮未找到');
        return;
    }
    
    // 检查模态框是否存在，如果不存在则创建简单的提示
    if (!saveTaskModalEl) {
        console.warn('保存任务模态框未找到，将使用简单提示');
    }
    if (!myTasksModalEl) {
        console.warn('我的任务模态框未找到，将使用简单提示');
    }
    
    // 如果关键元素都不存在，则退出
    if (!saveTaskBtn && !myTasksBtn) {
        console.error('任务功能所需的核心元素都未找到');
        return;
    }

    // 动态获取模态框实例的函数
    function getSaveTaskModal() {
        const el = document.getElementById('saveTaskModal');
        if (!el) {
            console.warn('saveTaskModal 元素未找到，可能需要刷新页面缓存');
            return null;
        }
        return bootstrap.Modal.getInstance(el) || new bootstrap.Modal(el);
    }
    
    function getMyTasksModal() {
        const el = document.getElementById('myTasksModal');
        if (!el) {
            console.warn('myTasksModal 元素未找到，可能需要刷新页面缓存');
            return null;
        }
        return bootstrap.Modal.getInstance(el) || new bootstrap.Modal(el);
    }
    
    // 等待元素出现的函数
    function waitForElement(selector, timeout = 5000) {
        return new Promise((resolve) => {
            const element = document.querySelector(selector);
            if (element) {
                resolve(element);
                return;
            }
            
            const observer = new MutationObserver((mutations) => {
                const element = document.querySelector(selector);
                if (element) {
                    observer.disconnect();
                    resolve(element);
                }
            });
            
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
            
            setTimeout(() => {
                observer.disconnect();
                resolve(null);
            }, timeout);
        });
    }
    
    // 动态获取表单元素的函数
    function getFormElements() {
        return {
            saveTaskForm: document.getElementById('saveTaskForm'),
            taskNameInput: document.getElementById('taskNameInput'),
            taskNameError: document.getElementById('taskNameError'),
            tasksListContainer: document.getElementById('tasksListContainer'),
            tasksPaginationContainer: document.getElementById('tasksPaginationContainer')
        };
    }
    
    const formElements = getFormElements();
    // console.log('表单元素检查:', formElements);

    // --- 核心功能函数 ---

    /**
     * 检查当前用户的登录状态
     */
    async function checkCurrentUserStatus() {
        try {
            const data = await fetchAPI('/check_login_status');
            if (data.logged_in && data.user) {
                window.currentUser = data.user;
                // console.log('用户状态更新成功:', window.currentUser);
            } else {
                window.currentUser = null;
                // console.log('用户未登录');
            }
        } catch (error) {
            console.error('检查登录状态失败:', error);
            window.currentUser = null;
        }
    }

    /**
     * 检查当前页面是否有未保存的更改。
     */
    function isPageDirty() {
        // 如果当前有结果，但尚未关联到已保存任务，则认为是"脏"的
        if (window.currentResults && window.currentResults.length > 0 && !currentLoadedTask) {
            return true;
        }
        return false;
    }

    /**
     * 更新保存按钮的状态和文本
     */
    function updateSaveButtonState() {
        if (currentLoadedTask) {
            saveTaskBtn.textContent = '更新任务';
            saveTaskBtn.classList.remove('btn-success');
            saveTaskBtn.classList.add('btn-warning');
        } else {
            saveTaskBtn.textContent = '保存结果到用户';
            saveTaskBtn.classList.remove('btn-warning');
            saveTaskBtn.classList.add('btn-success');
        }
    }

    /**
     * 根据API返回的数据，重新渲染主页面的结果表格
     * @param {Array} resultsData - 任务的结果数据
     */
    function renderResultsToTable(resultsData) {
        if (window.updateResultsTable) {
            window.currentResults = resultsData;
            window.updateResultsTable(resultsData);
            if (window.updateResultsOverview) window.updateResultsOverview();
            if (window.updateStats) window.updateStats();
        } else {
            console.error('关键渲染函数 window.updateResultsTable 未定义。');
            alert('无法加载任务数据：页面渲染函数缺失。');
        }
    }

    // --- "保存/更新" 流程 ---
    
    if (saveTaskBtn) {
        saveTaskBtn.addEventListener('click', async function() {
            // console.log('💾 保存任务按钮被点击，当前加载的任务:', currentLoadedTask);
            
            // 如果用户状态为空，尝试重新检查登录状态
            if (!window.currentUser) {
                // console.log('保存任务时用户状态为空，重新检查登录状态...');
                await checkCurrentUserStatus();
            }
            
            if (!window.currentUser) {
                if (window.showToast) {
                    window.showToast('请先登录再使用此功能。', 'warning');
                } else {
                    alert('请先登录再使用此功能。');
                }
                return;
            }

            if (currentLoadedTask) {
                // 更新模式
                if (!confirm('确定要用当前表格中的数据覆盖已保存的任务吗？')) return;
                
                // console.log('🔄 更新现有任务，收集状态信息...');
                
                // 收集所有状态信息（与新建任务相同的逻辑）
                const extendedData = {
                    results: window.currentResults,
                    poiStates: {},
                    webIntelligenceStates: {},
                    timestamp: Date.now()
                };

                // 从calibration模块收集POI状态
                if (window.calibrationPanel && typeof window.calibrationPanel.getAddressStates === 'function') {
                    try {
                        const poiStates = window.calibrationPanel.getAddressStates();
                        extendedData.poiStates = poiStates;
                        // console.log('💾 已收集POI状态', Object.keys(poiStates).length, '条记录');
                        if (Object.keys(poiStates).length > 0) {
                            // console.log('💾 POI状态详情:', poiStates);
                        }
                    } catch (e) {
                        console.warn('⚠️ 收集POI状态失败:', e);
                    }
                } else {
                    // console.log('ℹ️ calibrationPanel未初始化，POI状态收集为空');
                }

                // 从webIntelligence模块收集网络信息状态
                if (window.webIntelligence && typeof window.webIntelligence.getAddressStates === 'function') {
                    try {
                        extendedData.webIntelligenceStates = window.webIntelligence.getAddressStates();
                        // console.log('💾 已收集网络信息状态', Object.keys(extendedData.webIntelligenceStates).length, '条记录');
                        if (Object.keys(extendedData.webIntelligenceStates).length > 0) {
                            // console.log('💾 网络信息状态详情:', extendedData.webIntelligenceStates);
                        }
                    } catch (e) {
                        console.warn('⚠️ 收集网络信息状态失败:', e);
                    }
                } else {
                    // console.log('ℹ️ webIntelligence未初始化，跳过网络信息状态收集');
                }
                
                try {
                    const data = await fetchAPI(`/tasks/${currentLoadedTask.id}`, {
                        method: 'PUT',
                        body: JSON.stringify({ result_data: extendedData })
                    });
                    window.showToast(data.success ? '任务更新成功！' : (data.error || '任务更新失败'), data.success ? 'success' : 'danger');
                    if (data.success) {
                        const tracking = window.currentGeocodingTracking || {};
                        trackInteraction('task_saved', {
                            triggerOrigin: 'human_task_save',
                            geocodingTaskId: tracking.task_id,
                            clientActionId: tracking.client_action_id,
                            success: true,
                        });
                    }
                } catch (error) {
                    console.error('更新任务失败:', error);
                    window.showToast('网络错误，更新失败', 'danger');
                }
            } else {
                // 保存模式
                const taskNameInputEl = document.getElementById('taskNameInput');
                const taskNameErrorEl = document.getElementById('taskNameError');

                // 选择默认任务名称：优先使用右上角显示（LLM建议名称），否则回退到兼容元素
                const taskNameDisplayEl = document.getElementById('taskNameDisplay');
                const legacyNameCamelEl = document.getElementById('locationNameDisplay');
                const legacyNameKebabEl = document.getElementById('location-name-display');
                let defaultTaskName = '';
                if (taskNameDisplayEl && taskNameDisplayEl.textContent && taskNameDisplayEl.textContent.trim() && taskNameDisplayEl.textContent.trim() !== '未命名任务') {
                    defaultTaskName = taskNameDisplayEl.textContent.trim();
                } else if (legacyNameCamelEl && legacyNameCamelEl.textContent && legacyNameCamelEl.textContent.trim()) {
                    defaultTaskName = legacyNameCamelEl.textContent.trim();
                } else if (legacyNameKebabEl && legacyNameKebabEl.textContent && legacyNameKebabEl.textContent.trim()) {
                    defaultTaskName = legacyNameKebabEl.textContent.trim();
                }

                if (taskNameInputEl) {
                    taskNameInputEl.value = defaultTaskName;
                    taskNameInputEl.classList.remove('is-invalid');
                }
                if (taskNameErrorEl) {
                    taskNameErrorEl.textContent = '';
                }
                let saveTaskModal = getSaveTaskModal();
                if (saveTaskModal) {
                    saveTaskModal.show();
                } else {
                    // console.log('保存任务模态框不存在，等待元素出现...');
                    window.showToast('正在加载保存任务对话框...', 'info');
                    
                    try {
                        const modalElement = await waitForElement('#saveTaskModal', 3000);
                        if (modalElement) {
                            // console.log('等待后找到了保存任务模态框');
                            saveTaskModal = new bootstrap.Modal(modalElement);
                            saveTaskModal.show();
                        } else {
                            // console.log('等待超时，建议刷新页面');
                            window.showToast('页面元素加载异常，请刷新页面（Ctrl+F5）', 'warning');
                        }
                    } catch (error) {
                        console.error('等待模态框出现时出错:', error);
                        window.showToast('加载失败，请刷新页面', 'error');
                    }
                }
            }
        });
    }

    const saveTaskForm = document.getElementById('saveTaskForm');
    if (saveTaskForm) {
        saveTaskForm.addEventListener('submit', async function(event) {
            event.preventDefault();
            const taskNameInputEl = document.getElementById('taskNameInput');
            const taskNameErrorEl = document.getElementById('taskNameError');
            const taskName = taskNameInputEl ? taskNameInputEl.value.trim() : '';
            if (!taskName) {
                if (taskNameErrorEl) taskNameErrorEl.textContent = '任务名称不能为空。';
                if (taskNameInputEl) taskNameInputEl.classList.add('is-invalid');
                return;
            }

            try {
                // 收集所有状态信息
                const extendedData = {
                    results: window.currentResults,
                    poiStates: {},
                    webIntelligenceStates: {},
                    timestamp: Date.now()
                };

                // 从calibration模块收集POI状态
                if (window.calibrationPanel && typeof window.calibrationPanel.getAddressStates === 'function') {
                    try {
                        const poiStates = window.calibrationPanel.getAddressStates();
                        extendedData.poiStates = poiStates;
                        // console.log('💾 已收集POI状态', Object.keys(poiStates).length, '条记录');
                        if (Object.keys(poiStates).length > 0) {
                            // console.log('💾 POI状态详情:', poiStates);
                        }
                    } catch (e) {
                        console.warn('⚠️ 收集POI状态失败:', e);
                    }
                } else {
                    // console.log('ℹ️ calibrationPanel未初始化，POI状态收集为空');
                    // console.log('ℹ️ 提示：如果您使用了地址查找工具，请先点击"逐条查看与校准"按钮激活功能');
                }

                // 从webIntelligence模块收集网络信息状态
                if (window.webIntelligence && typeof window.webIntelligence.getAddressStates === 'function') {
                    try {
                        extendedData.webIntelligenceStates = window.webIntelligence.getAddressStates();
                        // console.log('💾 已收集网络信息状态', Object.keys(extendedData.webIntelligenceStates).length, '条记录');
                        // console.log('💾 网络信息状态详情:', extendedData.webIntelligenceStates);
                    } catch (e) {
                        console.warn('⚠️ 收集网络信息状态失败:', e);
                    }
                } else {
                    // console.log('ℹ️ webIntelligence未初始化，跳过网络信息状态收集');
                }

                const data = await fetchAPI('/tasks/', {
                    method: 'POST',
                    body: JSON.stringify({ task_name: taskName, result_data: extendedData })
                });

                if (data.success) {
                    window.showToast('任务保存成功！', 'success');
                    const tracking = window.currentGeocodingTracking || {};
                    trackInteraction('task_saved', {
                        triggerOrigin: 'human_task_save',
                        geocodingTaskId: tracking.task_id,
                        clientActionId: tracking.client_action_id,
                        success: true,
                    });
                    const saveTaskModal = getSaveTaskModal();
                    if (saveTaskModal) saveTaskModal.hide();
                    currentLoadedTask = { id: data.task_id, name: taskName };
                    updateSaveButtonState();
                } else {
                    if (taskNameErrorEl) taskNameErrorEl.textContent = data.error || '保存失败';
                    if (taskNameInputEl) taskNameInputEl.classList.add('is-invalid');
                }
            } catch (error) {
                console.error('保存任务失败:', error);
                window.showToast('网络错误，保存失败', 'danger');
            }
        });
    }

    // --- "我的任务列表" 流程 ---

    myTasksBtn.addEventListener('click', async function() {
        // console.log('我的任务按钮被点击');
        // console.log('当前用户状态:', window.currentUser);
        
        // 如果用户状态为空，尝试重新检查登录状态
        if (!window.currentUser) {
            // console.log('用户状态为空，重新检查登录状态...');
            await checkCurrentUserStatus();
            // console.log('重新检查后的用户状态:', window.currentUser);
        }
        
        if (!window.currentUser) {
            // console.log('用户未登录，显示提示');
            if (window.showToast) {
                window.showToast('请先登录', 'warning');
            } else {
                alert('请先登录');
            }
            return;
        }
        
        let myTasksModal = getMyTasksModal();
        if (myTasksModal) {
            // console.log('显示我的任务模态框');
            myTasksModal.show();
            fetchAndRenderTasks(__myTasksPage, __myTasksPerPage);
        } else {
            // console.log('我的任务模态框不存在，等待元素出现...');
            window.showToast('正在加载我的任务...', 'info');
            
            try {
                const modalElement = await waitForElement('#myTasksModal', 3000);
                if (modalElement) {
                    // console.log('等待后找到了我的任务模态框');
                    myTasksModal = new bootstrap.Modal(modalElement);
                    myTasksModal.show();
                    fetchAndRenderTasks(__myTasksPage, __myTasksPerPage);
                } else {
                    // console.log('等待超时，建议刷新页面');
                    if (window.showToast) {
                        window.showToast('页面元素加载异常，请刷新页面（Ctrl+F5）', 'warning');
                    } else {
                        alert('页面元素加载异常，请刷新页面（Ctrl+F5）');
                    }
                }
            } catch (error) {
                console.error('等待模态框出现时出错:', error);
                window.showToast('加载失败，请刷新页面', 'error');
            }
        }
    });
    
    async function fetchAndRenderTasks(page = 1, per_page = 10) {
        const tasksListContainer = document.getElementById('tasksListContainer');
        const tasksPaginationContainer = document.getElementById('tasksPaginationContainer');
        // 同步模块级分页状态
        __myTasksPage = page;
        __myTasksPerPage = per_page;
        
        if (!tasksListContainer) {
            console.warn('任务列表容器不存在，跳过渲染');
            return;
        }
        
        tasksListContainer.innerHTML = '<p class="text-center">正在加载...</p>';
        try {
            const tasks = await fetchAPI(`/tasks/?page=${page}&per_page=${per_page}`);
            
            if (tasks.length === 0) {
                // 如果不是第一页，则自动回退到上一页
                if (page > 1) {
                    fetchAndRenderTasks(page - 1, per_page);
                    return;
                }
                // 第1页也为空，说明整体没有任务
                tasksListContainer.innerHTML = '<p class="text-center text-muted">您还没有保存任何任务。</p>';
                if (tasksPaginationContainer) tasksPaginationContainer.innerHTML = '';
                return;
            }

            let tasksHtml = '<ul class="list-group">';
            tasks.forEach(task => {
                tasksHtml += `
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        <div>
                            <strong class="d-block">${escapeHtml(task.task_name)}</strong>
                            <small class="text-muted">更新于: ${escapeHtml(task.updated_at)}</small>
                        </div>
                        <div>
                            <button class="btn btn-primary btn-sm me-2 btn-load-task" data-task-id="${task.id}">加载</button>
                            <button class="btn btn-danger btn-sm btn-delete-task" data-task-id="${task.id}">删除</button>
                        </div>
                    </li>`;
            });
            tasksHtml += '</ul>';
            tasksListContainer.innerHTML = tasksHtml;
            if (tasksPaginationContainer) {
                const isPrevDisabled = page <= 1;
                const isNextDisabled = tasks.length < per_page; // 小于每页条数，视为最后一页
                tasksPaginationContainer.innerHTML = `
                    <nav aria-label="Tasks pagination">
                        <ul class="pagination mb-0">
                            <li class="page-item ${isPrevDisabled ? 'disabled' : ''}">
                                <a class="page-link tasks-prev-page" href="#" aria-label="Previous">
                                    <span aria-hidden="true">&laquo;</span>
                                    <span class="visually-hidden">上一页</span>
                                </a>
                            </li>
                            <li class="page-item disabled"><span class="page-link">第 ${page} 页</span></li>
                            <li class="page-item ${isNextDisabled ? 'disabled' : ''}">
                                <a class="page-link tasks-next-page" href="#" aria-label="Next">
                                    <span aria-hidden="true">&raquo;</span>
                                    <span class="visually-hidden">下一页</span>
                                </a>
                            </li>
                        </ul>
                    </nav>`;

                // 若当前页条数等于每页条数，进一步探测下一页是否存在
                if (!isNextDisabled) {
                    try {
                        const probeData = await fetchAPI(`/tasks/?page=${page + 1}&per_page=${per_page}`);
                        if (probeData && (!Array.isArray(probeData) || probeData.length === 0)) {
                            const nextLi = tasksPaginationContainer.querySelector('.tasks-next-page')?.closest('.page-item');
                            if (nextLi) nextLi.classList.add('disabled');
                        }
                    } catch (e) {
                        // 探测失败时保持现状，不影响主流程
                    }
                }
            }

        } catch (error) {
            console.error('获取任务列表失败:', error);
            if (tasksListContainer) tasksListContainer.innerHTML = '<p class="text-center text-danger">加载失败，请重试。</p>';
        }
    }

    // --- "加载"与"删除"的事件代理 ---

    // 使用事件代理，监听document上的点击事件
    document.addEventListener('click', function(event) {
        const tasksListContainer = document.getElementById('tasksListContainer');
        if (!tasksListContainer || !tasksListContainer.contains(event.target)) {
            return;
        }
            const target = event.target;
            const taskId = target.dataset.taskId;

            if (target.classList.contains('btn-load-task')) {
                if (isPageDirty() && !confirm('当前有未保存的更改，加载新任务将覆盖现有内容，是否继续？')) return;
                loadTask(taskId);
            }

            if (target.classList.contains('btn-delete-task')) {
                if (confirm('确定要永久删除这个任务吗？')) deleteTask(taskId);
            }
    });

    // 分页按钮事件代理（作用于整个文档，捕获模态框中的点击）
    document.addEventListener('click', function(event) {
        const prevLink = event.target.closest('.tasks-prev-page');
        const nextLink = event.target.closest('.tasks-next-page');
        if (!prevLink && !nextLink) return;

        event.preventDefault();
        const li = (prevLink || nextLink).closest('.page-item');
        if (li && li.classList.contains('disabled')) return;

        if (prevLink) {
            const newPage = Math.max(1, (__myTasksPage || 1) - 1);
            fetchAndRenderTasks(newPage, __myTasksPerPage || 10);
            return;
        }
        if (nextLink) {
            const newPage = (__myTasksPage || 1) + 1;
            fetchAndRenderTasks(newPage, __myTasksPerPage || 10);
            return;
        }
    });

    async function loadTask(taskId) {
        try {
            const taskData = await fetchAPI(`/tasks/${taskId}`);
            
            // 处理新的数据结构（包含状态信息）或旧的数据结构（只有结果）
            let resultsData;
            let poiStates = {};
            let webIntelligenceStates = {};
            
            if (taskData.result_data && taskData.result_data.results) {
                // 新格式：包含状态信息
                resultsData = taskData.result_data.results;
                poiStates = taskData.result_data.poiStates || {};
                webIntelligenceStates = taskData.result_data.webIntelligenceStates || {};
                // console.log('📥 加载任务包含状态信息', { poiStates, webIntelligenceStates });
            } else {
                // 旧格式：只有结果数据
                resultsData = taskData.result_data;
                // console.log('📥 加载任务为旧格式，无状态信息');
            }
            
            // 调试：检查结果数据结构（临时）
            if (Array.isArray(resultsData) && resultsData.length > 0 && resultsData[0].results) {
                // console.log('📊 任务数据结构: 地址数量', resultsData.length, '第一个地址的API结果数量', resultsData[0].results.length);
            }
            
            renderResultsToTable(resultsData);
            
            // 恢复POI和网络信息状态
            if (window.calibrationPanel && typeof window.calibrationPanel.restoreAddressStates === 'function') {
                try {
                    window.calibrationPanel.restoreAddressStates(poiStates);
                    // console.log('✅ 已恢复POI状态');
                } catch (e) {
                    console.warn('⚠️ 恢复POI状态失败:', e);
                }
            } else {
                // console.log('ℹ️ calibrationPanel未初始化，跳过POI状态恢复');
            }
            
            if (window.webIntelligence && typeof window.webIntelligence.restoreAddressStates === 'function') {
                try {
                    window.webIntelligence.restoreAddressStates(webIntelligenceStates);
                    // console.log('✅ 已恢复网络信息状态');
                } catch (e) {
                    console.warn('⚠️ 恢复网络信息状态失败:', e);
                }
            } else {
                // console.log('ℹ️ webIntelligence未初始化，跳过网络信息状态恢复');
            }
            
            currentLoadedTask = { id: taskData.id, name: taskData.task_name };
            // 同步更新右上角任务名称显示（新旧元素兼容）
            const taskNameDisplayEl = document.getElementById('taskNameDisplay');
            if (taskNameDisplayEl) taskNameDisplayEl.textContent = taskData.task_name;
            const legacyNameCamelEl = document.getElementById('locationNameDisplay');
            if (legacyNameCamelEl) legacyNameCamelEl.textContent = taskData.task_name;
            const legacyNameKebabEl = document.getElementById('location-name-display');
            if (legacyNameKebabEl) legacyNameKebabEl.textContent = taskData.task_name;

            
            
            updateSaveButtonState();
            // 稳健地关闭“我的任务”模态框
            const myTasksModalEl = document.getElementById('myTasksModal');
            if (myTasksModalEl) {
                // 清除可能残留的 aria-hidden 与样式，避免关闭按钮失效
                myTasksModalEl.removeAttribute('aria-hidden');
                myTasksModalEl.style.removeProperty('display');
                const myTasksModal = bootstrap.Modal.getInstance(myTasksModalEl) || new bootstrap.Modal(myTasksModalEl);
                myTasksModal.hide();
                // 关闭后移除 backdrop，防止遮罩残留导致交互被拦截
                setTimeout(() => {
                    document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
                    document.body.classList.remove('modal-open');
                    document.body.style.removeProperty('padding-right');
                }, 50);
            }
            window.showToast(`任务 "${taskData.task_name}" 已加载`, 'info');

        } catch (error) {
            console.error(`加载任务 #${taskId} 失败:`, error);
            console.error('任务数据:', taskData);
            window.showToast(`加载任务 #${taskId} 失败: ${error.message}`, 'danger');
        }
    }
    
    async function deleteTask(taskId) {
        try {
            await fetchAPI(`/tasks/${taskId}`, { method: 'DELETE' });
            window.showToast('任务删除成功', 'success');
            fetchAndRenderTasks(1);
            if (currentLoadedTask && currentLoadedTask.id == taskId) {
                currentLoadedTask = null;
                updateSaveButtonState();
            }
        } catch (error) {
            console.error(`删除任务 #${taskId} 失败:`, error);
            window.showToast(error.message, 'danger');
        }
    }
    
    // 页面重置时，也应该重置任务状态
    const clearResultsBtn = document.getElementById('clear-results-btn');
    if(clearResultsBtn) {
        clearResultsBtn.addEventListener('click', function() {
            if(currentLoadedTask) {
                currentLoadedTask = null;
                updateSaveButtonState();
            }
        });
    }
}
