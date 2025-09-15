// 统一的页面初始化函数
let hasInitialized = false;

function initializePage() {
    console.log('initializePage 被调用');
    if (hasInitialized) {
        console.log('页面已经初始化过，跳过');
        return;
    }
    
    console.log('页面开始统一初始化...');
    hasInitialized = true;
    
    // 初始化搜索表单
    const searchForm = document.getElementById('smartSearchForm');
    if (searchForm) {
        searchForm.addEventListener('submit', handleSmartSearch);
        console.log('搜索表单初始化完成');
    }
    
    // 初始化表格
    const tbody = document.getElementById('cascadeResultsBody');
    if (tbody) {
        // 移除可能存在的旧事件监听器
        const newTbody = tbody.cloneNode(true);
        tbody.parentNode.replaceChild(newTbody, tbody);
        
        // 添加新的事件监听器
        if (typeof window.globalCascadeClickHandler === 'function') {
            newTbody.addEventListener('click', window.globalCascadeClickHandler);
        } else {
            console.error('Error: window.globalCascadeClickHandler is not defined. Table click handling will not work.');
        }
        console.log('表格事件监听初始化完成');
    }
    
    // 初始化地图
    if (typeof window.initializeMapGlobal === 'function') {
        window.initializeMapGlobal();
        console.log('主地图通过 window.initializeMapGlobal 初始化调用完成');
    } else {
        console.error('Error: window.initializeMapGlobal is not defined. Map will not initialize.');
    }
    
    // 初始化API选择
    const cascadeApi = document.getElementById('cascadeApi');
    if (cascadeApi) {
        cascadeApi.addEventListener('change', function() {
            if (this.checked) {
                console.log('已选择级联编码模式');
            }
        });
    }
    
    // 初始化其他功能
    if (typeof window.initialize === 'function') {
        window.initialize();
    }
    
    // 初始化API按钮 (注释掉此块)
    if (typeof window.initializeApiButtons === 'function') {
        window.initializeApiButtons();
    }

    // 调用 index.html 中定义的页面特性初始化函数
    console.log('=== 检查页面特性初始化函数 ===');
    console.log('当前时间戳:', Date.now());
    console.log('window.initializePageSpecificFeatures 类型:', typeof window.initializePageSpecificFeatures);
    console.log('window.initializePageSpecificFeatures 值:', window.initializePageSpecificFeatures);
    console.log('window 对象中所有 initialize 相关的键:', Object.keys(window).filter(key => key.includes('initialize')));
    console.log('script.js 是否已加载:', typeof window.webIntelligence !== 'undefined');
    
    if (typeof window.initializePageSpecificFeatures === 'function') {
        console.log('=== 调用页面特性初始化函数 ===');
        try {
            window.initializePageSpecificFeatures();
            console.log('页面特性初始化函数调用完成');
        } catch (error) {
            console.error('页面特性初始化函数调用失败:', error);
        }
    } else {
        console.error('Error: window.initializePageSpecificFeatures is not defined. Some page-specific UI elements may not be initialized.');
        console.log('可用的全局函数:', Object.keys(window).filter(key => key.includes('initialize')));
        
        // 尝试延迟调用
        console.log('尝试延迟调用...');
        setTimeout(() => {
            console.log('延迟检查 - window.initializePageSpecificFeatures 类型:', typeof window.initializePageSpecificFeatures);
            if (typeof window.initializePageSpecificFeatures === 'function') {
                console.log('延迟调用页面特性初始化函数...');
                window.initializePageSpecificFeatures();
            }
        }, 100);
    }
    
    console.log('页面初始化完成');
}

// 初始化按钮事件
function initializeButtons() {
    // 智能编码按钮的事件绑定已在其他地方处理
}

// 确保只在 DOMContentLoaded 时初始化一次
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializePage);
} else {
    // 如果 DOMContentLoaded 已经触发，直接初始化
    initializePage();
} 