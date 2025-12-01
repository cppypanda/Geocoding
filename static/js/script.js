// 主脚本文件 - 导入所有必要的模块
import { updateUserBar, initializeAuthForms, showLoginModal } from './modules/auth.js';
import { showToast, convertCoordinates, checkUserPoints } from './modules/utils.js';
import { displayCascadeResults } from './modules/ui.js';
import { initializeMap, initializeResultsOverviewMap, updateResultsOverviewMapMarkers, ensureResultsOverviewMap, ensureCalibrationMap } from './modules/map.js';
import { initializeCalibrationPanel } from './modules/calibration.js';
import { handleSmartSearch, cleanAddressText, initializeFeatures, setWebIntelligenceAddress } from './modules/features.js';
import { webIntelligence } from './modules/web-intelligence.js';
import { initializeTaskManager } from './task_manager.js';
import { initializeAddressCleaner } from './modules/address-cleaner.js';
import { initializeAddressInput } from './modules/address-input.js';
import { handleGeocodeClick, handleAutoSelect } from './modules/geocoding.js';
import { ENDPOINTS, SELECTORS } from './modules/constants.js';
import { startSmartCalibration } from './modules/smart-calibration.js';
import { initializeMapSearch, getPoiResults } from './modules/map-search.js';
import { initializeNotifications } from './modules/notifications.js';
import { exportData, fetchAPI } from './modules/api.js';

// 确保模块在全局可用
window.webIntelligence = webIntelligence;
window.updateUserBar = updateUserBar;
window.displayCascadeResults = displayCascadeResults;
window.handleSmartSearch = handleSmartSearch;
window.showToast = showToast;
window.cleanAddressText = cleanAddressText;

// 全局状态
window.currentUser = null; // 使用 window.currentUser 确保全局可访问
window.actionAfterLogin = null; // 用于存储登录后需要执行的操作
let cascadeResults = [];
let itemCalibrationMap = null;
let calibrationPanel = null;
let __resultsPage = 1;
let __resultsPerPage = 15;

// 级联结果表格点击处理
function handleCascadeTableClick(event) {
    const button = event.target.closest('button');
    if (!button) return;
    
    // 处理各种按钮点击事件
    if (button.onclick) {
        // 让现有的onclick处理器处理
        return;
    }
    
    // 处理其他按钮逻辑...
}

// 页面特性初始化
function initializePageSpecificFeatures() {
    
    // 初始化模态框和其他UI组件
    initializeModals();
    
    // 初始化按钮事件
    initializeButtons();
    
}

// 初始化模态框
function initializeModals() {
    // 登录模态框相关的初始化会在auth模块中处理
}

// 初始化按钮事件
function initializeButtons() {
    // 主要的编码按钮
    const normalGeocodeBtn = document.getElementById('normalGeocodeBtn');
    const smartGeocodeBtn = document.getElementById('smartGeocodeBtn');
    
    if (normalGeocodeBtn) {
        normalGeocodeBtn.addEventListener('click', () => {
            handleGeocode('normal');
            // 点击“地理编码”后，显式显示并启用“智能校准”按钮
            try {
                const calibrateBtn = document.getElementById('smartCalibrationBtn');
                if (calibrateBtn) {
                    calibrateBtn.style.display = '';
                    calibrateBtn.disabled = false;
                }
                window.__lastGeocodeAction = 'normal';
            } catch (e) { }
        });
    }
    
    if (smartGeocodeBtn) {
        smartGeocodeBtn.addEventListener('click', () => {
            if (!checkUserPoints()) return;

            // handleGeocode('smart'); // 旧的逻辑
            
            // 新的“一键智能编码”逻辑
            const geocodeBtn = document.getElementById('normalGeocodeBtn');
            const calibrateBtn = document.getElementById('smartCalibrationBtn');
            const resultsTableBody = document.getElementById('cascadeResultsBody');

            if (!geocodeBtn || !calibrateBtn || !resultsTableBody) {
                showToast('页面组件不完整，无法执行一键操作。', 'error');
                return;
            }

            // “智能编码”已包含校准流程，隐藏“智能校准”按钮
            try {
                calibrateBtn.style.display = 'none';
                window.__lastGeocodeAction = 'oneclick';
            } catch (e) { }

            // 1. 禁用按钮，防止重复点击
            smartGeocodeBtn.disabled = true;
            smartGeocodeBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 处理中...';

            // 2. 触发地理编码
            geocodeBtn.click();
            showToast('多源编码已启动...', 'info');

            // 3. 设置观察器以等待编码结果
            const observer = new MutationObserver((mutationsList, obs) => {
                // 检查是否有子节点（即结果行）被添加
                if (resultsTableBody.children.length > 0) {
                    showToast('多源编码完成，即将开始智能校准。', 'success');
                    
                    // 4. 触发智能校准
                    // 加一个短暂的延迟，确保UI渲染完成
                    setTimeout(() => {
                        calibrateBtn.click();
                    }, 500);

                    // 5. 清理工作
                    obs.disconnect(); // 停止观察
                    
                    // 恢复按钮状态
                    smartGeocodeBtn.disabled = false;
                    smartGeocodeBtn.innerHTML = '<i class="bi bi-stars"></i> 智能编码';
                }
            });

            // 配置观察器：观察子节点的变动
            const config = { childList: true };
            observer.observe(resultsTableBody, config);
        });
    }
    
    // 充值相关按钮
    const showRechargeModalBtn = document.getElementById('showRechargeModalBtn');
    const rechargeBtn = document.getElementById('rechargeBtn');
    // 充值流程DOM
    const rechargePackageList = document.getElementById('rechargePackageList');
    const paymentMethodList = document.getElementById('paymentMethodList');
    const amountToPayAlipay = document.getElementById('amountToPayAlipay');
    const amountToPayWechat = document.getElementById('amountToPayWechat');
    const agreeRechargeTerms = document.getElementById('agreeRechargeTerms');
    const initiateAlipayBtn = document.getElementById('initiateAlipayBtn');
    const confirmWechatPaymentBtn = document.getElementById('confirmWechatPaymentBtn');

    // 微信支付相关DOM
    const alipayInfoArea = document.getElementById('alipay-info-area');
    const wechatQrArea = document.getElementById('wechat-qr-area');
    const paymentQrCode = document.getElementById('paymentQrCode');
    const orderNumberDisplay = document.getElementById('orderNumberDisplay');
    const copyOrderNumberBtn = document.getElementById('copyOrderNumberBtn');

    // 充值流程状态
    let selectedPackageId = null;
    let selectedPaymentMethod = null; // 'alipay' | 'wechat'
    let currentRechargeOrder = null; // 存储当前创建的订单

    function resetRechargeFlow() {
        selectedPackageId = null;
        selectedPaymentMethod = null;
        currentRechargeOrder = null;
        // 视觉重置
        if (rechargePackageList) {
            rechargePackageList.querySelectorAll('.recharge-package-card').forEach(card => card.classList.remove('selected'));
        }
        if (paymentMethodList) {
            paymentMethodList.querySelectorAll('.payment-method-btn').forEach(btn => {
                btn.classList.remove('active');
                btn.disabled = true;
            });
        }
        if (amountToPayAlipay) amountToPayAlipay.textContent = '0.00';
        if (amountToPayWechat) amountToPayWechat.textContent = '0.00';
        if (orderNumberDisplay) orderNumberDisplay.value = '';

        // UI 切换
        if (alipayInfoArea) alipayInfoArea.style.display = 'none';
        if (wechatQrArea) wechatQrArea.style.display = 'none';
        if (initiateAlipayBtn) initiateAlipayBtn.style.display = 'none';
        if (confirmWechatPaymentBtn) confirmWechatPaymentBtn.style.display = 'none';

        updatePaymentButtonStates();
    }

    function updatePaymentButtonStates() {
        const termsOk = !!(agreeRechargeTerms && agreeRechargeTerms.checked);
        const ready = !!(selectedPackageId && selectedPaymentMethod);
        if (initiateAlipayBtn) initiateAlipayBtn.disabled = !(termsOk && ready);
        if (confirmWechatPaymentBtn) confirmWechatPaymentBtn.disabled = !(termsOk && ready);
    }

    // 当打开充值模态时，重置流程
    if (showRechargeModalBtn) {
        showRechargeModalBtn.addEventListener('click', () => {
            // 显示充值模态框
            const modal = new bootstrap.Modal(document.getElementById('rechargeModal'));
            modal.show();
            // 延迟到模态显示后执行重置，避免闪烁
            setTimeout(resetRechargeFlow, 50);
        });
    }
    if (rechargeBtn) {
        rechargeBtn.addEventListener('click', () => {
            // 显示充值模态框
            const modal = new bootstrap.Modal(document.getElementById('rechargeModal'));
            modal.show();
            setTimeout(resetRechargeFlow, 50);
        });
    }

    // 套餐选择
    if (rechargePackageList) {
        rechargePackageList.addEventListener('click', (e) => {
            const card = e.target.closest('.recharge-package-card');
            if (!card) return;
            // 标记选中
            rechargePackageList.querySelectorAll('.recharge-package-card').forEach(el => el.classList.remove('selected'));
            card.classList.add('selected');
            selectedPackageId = card.getAttribute('data-package-id');
            currentRechargeOrder = null; // 套餐变更，清除已创建的订单
            // 选择套餐后，启用支付方式按钮
            if (paymentMethodList) {
                paymentMethodList.querySelectorAll('.payment-method-btn').forEach(btn => btn.disabled = false);
            }
            // 如果支付方式已选，则更新价格和UI
            if(selectedPaymentMethod) {
                updatePriceAndUIVisibility();
            }
            updatePaymentButtonStates();
        });
    }

    function updatePriceAndUIVisibility() {
        let priceText = '';
        try {
            const selectedCard = rechargePackageList && rechargePackageList.querySelector('.recharge-package-card.selected');
            if (selectedCard) {
                // 优先使用 class 选择器，兼容旧结构则使用 nth-child(3) 或 nth-child(2)
                const priceDiv = selectedCard.querySelector('.package-real-price') || 
                                 selectedCard.querySelector('div:nth-child(3)') || 
                                 selectedCard.querySelector('div:nth-child(2)');
                if (priceDiv) priceText = priceDiv.textContent || '';
            }
        } catch (e) {}
        const match = priceText.match(/([0-9]+(?:\.[0-9]{1,2})?)/);
        const parsedAmount = match ? parseFloat(match[1]).toFixed(2) : '0.00';
        
        // 无论是支付宝还是微信，都显示二维码区域
        const amountForQr = parsedAmount ? (Number(parsedAmount)).toString() : '';
        
        if (amountToPayWechat) amountToPayWechat.textContent = parsedAmount;
        if (alipayInfoArea) alipayInfoArea.style.display = 'none';
        if (wechatQrArea) wechatQrArea.style.display = 'block';
        
        // 隐藏旧的支付宝跳转按钮
        if (initiateAlipayBtn) initiateAlipayBtn.style.display = 'none';
        // 显示统一的确认按钮（复用 confirmWechatPaymentBtn）
        if (confirmWechatPaymentBtn) confirmWechatPaymentBtn.style.display = 'inline-block';
        
        if (selectedPaymentMethod === 'alipay') {
            setQrImageFor('alipay', amountForQr);
        } else if (selectedPaymentMethod === 'wechat') {
            setQrImageFor('wechat', amountForQr);
        }
        
        // 为选定的支付方式提前创建订单以显示订单号
        createRechargeOrderIfNeeded();
    }

    // 支付方式选择
    if (paymentMethodList) {
        paymentMethodList.addEventListener('click', async (e) => {
            const btn = e.target.closest('.payment-method-btn');
            if (!btn || btn.disabled) return;
            // 高亮当前选择
            paymentMethodList.querySelectorAll('.payment-method-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedPaymentMethod = btn.getAttribute('data-method');
            
            // 确保已选择套餐
            if (!selectedPackageId) {
                showToast('请先选择充值套餐', 'warning');
                return;
            }

            updatePriceAndUIVisibility();
            updatePaymentButtonStates();
        });
    }

    function setQrImageFor(method, amount) {
        if (!paymentQrCode) return;
        const basePath = '/static/images/payment';
        // 根据支付方式确定文件扩展名 (都使用 jpg)
        const extension = 'jpg';
        const fileName = amount ? `${amount}.${extension}` : '';
        const src = `${basePath}/${method}/${fileName}`;
        paymentQrCode.src = src;
    }

    // 协议勾选控制
    if (agreeRechargeTerms) {
        agreeRechargeTerms.addEventListener('change', updatePaymentButtonStates);
    }
    
    // 复制订单号
    if (copyOrderNumberBtn && orderNumberDisplay) {
        copyOrderNumberBtn.addEventListener('click', async () => {
            if (!orderNumberDisplay.value) {
                showToast('无可复制的订单号', 'warning');
                return;
            }
            try {
                await navigator.clipboard.writeText(orderNumberDisplay.value);
                showToast('订单号已复制', 'success');
            } catch (e) {
                orderNumberDisplay.select();
                document.execCommand && document.execCommand('copy');
                showToast('已尝试复制订单号', 'info');
            }
        });
    }

    async function createRechargeOrderIfNeeded() {
        if (currentRechargeOrder) return currentRechargeOrder; // 如果已创建订单，直接返回
        if (!selectedPackageId) return null;
        try {
            // 从 meta 标签获取 CSRF token
            const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
            
            const resp = await fetch('/create_recharge_order', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken // 添加 CSRF token
                },
                body: JSON.stringify({ 
                    package_id: selectedPackageId,
                    payment_method: selectedPaymentMethod
                })
            });
            if (resp.status === 401) {
                showToast('请先登录后再充值', 'warning');
                const loginModalElement = document.getElementById('loginRegisterModal');
                if (loginModalElement) {
                    new bootstrap.Modal(loginModalElement).show();
                }
                return null;
            }
            const data = await resp.json();
            if (!resp.ok || !data.success) {
                showToast(data.message || '创建订单失败', 'danger');
                return null;
            }
            const order = { order_number: data.order_number, amount: data.amount };
            
            currentRechargeOrder = order; // 缓存订单
            // 创建成功后立即显示订单号
            if (orderNumberDisplay) orderNumberDisplay.value = order.order_number;
            
            return order;
        } catch (err) {
            showToast('网络异常，创建订单失败', 'danger');
            return null;
        }
    }

    // 前往支付宝支付
    if (initiateAlipayBtn) {
        initiateAlipayBtn.addEventListener('click', async () => {
            if (!selectedPackageId || !selectedPaymentMethod) {
                showToast('请先选择套餐和支付方式', 'warning');
                return;
            }
            if (selectedPaymentMethod !== 'alipay') {
                showToast('暂不支持此支付方式，敬请期待', 'info');
                return;
            }

            initiateAlipayBtn.disabled = true;
            initiateAlipayBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 正在创建订单...';

            try {
                // 1. 创建订单
                const order = await createRechargeOrderIfNeeded();
                if (!order) {
                    throw new Error('创建订单失败');
                }
                
                initiateAlipayBtn.innerHTML = '<i class="bi bi-shield-lock"></i> 正在生成安全支付链接...';

                // 2. 获取支付链接
                const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
                const paymentResp = await fetch('/initiate_payment', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken // 添加 CSRF token
                    },
                    body: JSON.stringify({ order_number: order.order_number })
                });
                const paymentData = await paymentResp.json();
                if (!paymentResp.ok || !paymentData.success) {
                    throw new Error(paymentData.message || '获取支付链接失败');
                }

                // 3. 跳转到支付页面
                window.location.href = paymentData.payment_url;

            } catch (err) {
                showToast(err.message, 'danger');
                // 发生错误，重新启用按钮
                initiateAlipayBtn.disabled = false;
                initiateAlipayBtn.innerHTML = '<i class="bi bi-shield-check"></i> 前往支付宝安全支付';
            }
        });
    }

    // 确认支付（手动）- 复用 confirmWechatPaymentBtn
    if (confirmWechatPaymentBtn) {
        confirmWechatPaymentBtn.addEventListener('click', async () => {
            if (!selectedPackageId || !selectedPaymentMethod || !currentRechargeOrder) {
                showToast('请先选择套餐并生成订单', 'warning');
                return;
            }
            
            showToast('已记录您的支付意向，请等待管理员后台确认到账后为您发放积分。', 'info');
            
            // 关闭模态
            try {
                const el = document.getElementById('rechargeModal');
                if (el) {
                    const modal = bootstrap.Modal.getInstance(el) || new bootstrap.Modal(el);
                    modal.hide();
                }
            } catch (e) {}

            // 按钮状态在模态框关闭后由 resetRechargeFlow 重置
        });
    }
    
    // 免费积分按钮
    const showFreePointsModalBtn = document.getElementById('showFreePointsModalBtn');
    const bannerGetFreePointsLink = document.getElementById('bannerGetFreePointsLink');
    if (showFreePointsModalBtn) {
        showFreePointsModalBtn.addEventListener('click', () => {
            const modal = new bootstrap.Modal(document.getElementById('freePointsModal'));
            modal.show();
        });
    }
    if (bannerGetFreePointsLink) {
        bannerGetFreePointsLink.addEventListener('click', () => {
            const modal = new bootstrap.Modal(document.getElementById('freePointsModal'));
            modal.show();
        });
    }
    
    // 设置按钮
    const settingsDropdownLink = document.getElementById('settingsDropdownLink');
    if (settingsDropdownLink) {
        settingsDropdownLink.addEventListener('click', (e) => {
            e.preventDefault();
            const modal = new bootstrap.Modal(document.getElementById('settingsModal'));
            modal.show();
        });
    }
    
    // 使用教程按钮
    const showHelpModalBtn = document.getElementById('showHelpModalBtn');
    if (showHelpModalBtn) {
        showHelpModalBtn.addEventListener('click', (e) => {
            e.preventDefault();
            const modalEl = document.getElementById('helpModal');
            if (modalEl) {
                const modal = new bootstrap.Modal(modalEl);
                modal.show();
            }
        });
    }
    
    // 意见反馈按钮
    const showFeedbackModalBtn = document.getElementById('showFeedbackModalBtn');
    const feedbackFromFreePointsBtn = document.getElementById('feedbackFromFreePointsBtn');
    if (showFeedbackModalBtn) {
        showFeedbackModalBtn.addEventListener('click', (e) => {
            e.preventDefault();
            const modal = new bootstrap.Modal(document.getElementById('feedbackModal'));
            modal.show();
        });
    }
    if (feedbackFromFreePointsBtn) {
        feedbackFromFreePointsBtn.addEventListener('click', () => {
            const modal = new bootstrap.Modal(document.getElementById('feedbackModal'));
            modal.show();
        });
    }

    // 反馈表单交互
    const feedbackForm = document.getElementById('feedbackForm');
    const feedbackDescription = document.getElementById('feedbackDescription');
    const feedbackCharCount = document.getElementById('feedbackCharCount');
    const feedbackImagesInput = document.getElementById('feedbackImagesInput');
    const feedbackImageUploadArea = document.getElementById('feedbackImageUploadArea');
    const feedbackImagePreviewContainer = document.getElementById('feedbackImagePreviewContainer');
    const submitFeedbackBtn = document.getElementById('submitFeedbackBtn');
    const feedbackCategoryInput = document.getElementById('feedbackCategory');
    const feedbackMetadataInput = document.getElementById('feedbackMetadata');

    // 字数统计
    if (feedbackDescription && feedbackCharCount) {
        const updateCount = () => {
            try { feedbackCharCount.textContent = String(feedbackDescription.value.length); } catch (e) {}
        };
        feedbackDescription.addEventListener('input', updateCount);
        updateCount();
    }

    // 点击上传区域 -> 触发隐藏的文件选择
    if (feedbackImageUploadArea && feedbackImagesInput) {
        feedbackImageUploadArea.addEventListener('click', () => feedbackImagesInput.click());
    }

    // 预览图渲染
    function renderPreviews(files) {
        if (!feedbackImagePreviewContainer) return;
        feedbackImagePreviewContainer.innerHTML = '';
        const maxFiles = 3;
        const validFiles = Array.from(files || []).slice(0, maxFiles);
        validFiles.forEach(file => {
            const url = URL.createObjectURL(file);
            const img = document.createElement('img');
            img.src = url;
            img.style.maxWidth = '120px';
            img.style.maxHeight = '120px';
            img.style.borderRadius = '12px';
            img.onload = () => URL.revokeObjectURL(url);
            feedbackImagePreviewContainer.appendChild(img);
        });
    }

    if (feedbackImagesInput) {
        feedbackImagesInput.addEventListener('change', (e) => {
            const files = e.target.files;
            renderPreviews(files);
        });
    }

    // 提交反馈
    if (submitFeedbackBtn) {
        submitFeedbackBtn.addEventListener('click', async () => {
            const desc = (feedbackDescription?.value || '').trim();
            if (!desc) {
                showToast('反馈内容不能为空', 'warning');
                return;
            }

            submitFeedbackBtn.disabled = true;
            submitFeedbackBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 提交中...';

            // Grab files for later background upload
            const filesToUpload = (feedbackImagesInput && feedbackImagesInput.files && feedbackImagesInput.files.length > 0)
                ? Array.from(feedbackImagesInput.files).slice(0, 3)
                : [];

            try {
                // Step 1: Submit the feedback text first to get an ID
                const payload = { 
                    feedback_text: desc,
                    total_images: filesToUpload.length  // <<< Add this
                };
                const catVal = feedbackCategoryInput ? (feedbackCategoryInput.value || '').trim() : '';
                if (catVal) payload.category = catVal;
                const metaVal = feedbackMetadataInput ? (feedbackMetadataInput.value || '').trim() : '';
                if (metaVal) payload.metadata = metaVal;

                const initialData = await fetchAPI(ENDPOINTS.submitFeedback, {
                    method: 'POST',
                    body: JSON.stringify(payload)
                });

                if (!initialData.success) {
                    throw new Error(initialData.message || '提交反馈文本失败');
                }

                const feedbackId = initialData.feedback_id;

                // Step 2: Immediately confirm to user and reset UI
                showToast(initialData.message || '反馈已提交，感谢您的支持！', 'success');
                try {
                    const modalEl = document.getElementById('feedbackModal');
                    const modal = modalEl && (bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl));
                    modal && modal.hide();
                } catch (e) {}
                if (feedbackForm) feedbackForm.reset();
                if (feedbackImagePreviewContainer) feedbackImagePreviewContainer.innerHTML = '';
                if (feedbackCategoryInput) feedbackCategoryInput.value = '';
                if (feedbackMetadataInput) feedbackMetadataInput.value = '';

                // Step 3: Upload images in the background (fire and forget)
                if (filesToUpload.length > 0 && feedbackId) {
                    
                    const uploadFileWithRetry = async (file, feedbackId, retries = 2) => {
                        const formData = new FormData();
                        formData.append('image', file);
                        formData.append('feedback_id', feedbackId);

                        for (let i = 0; i <= retries; i++) {
                            try {
                                const uploadData = await fetchAPI(ENDPOINTS.uploadFeedbackImage, { method: 'POST', body: formData });
                                if (uploadData.success) {
                                    console.log(`Background image ${file.name} uploaded successfully.`);
                                    return; // Success, exit the loop
                                }
                                // If server responds with success: false, treat as a failure to retry
                                console.warn(`Attempt ${i + 1} failed for ${file.name}:`, uploadData.message);
                            } catch (err) {
                                console.error(`Attempt ${i + 1} threw an error for ${file.name}:`, err);
                            }
                        }
                        console.error(`Failed to upload image ${file.name} after ${retries + 1} attempts.`);
                    };

                    filesToUpload.forEach(file => {
                        // We don't await this promise, letting it run in the background.
                        uploadFileWithRetry(file, feedbackId);
                    });
                }

            } catch (e) {
                showToast(e.message || '提交失败，请检查网络', 'error');
            } finally {
                submitFeedbackBtn.disabled = false;
                submitFeedbackBtn.textContent = '确定';
            }
        });
    }

    // ===== 社交传播文案相关 =====
    const socialCopyText = document.getElementById('socialShareCopyText');
    const generateSocialCopyBtn = document.getElementById('generateSocialCopyBtn');
    const copySocialCopyBtn = document.getElementById('copySocialCopyBtn');
    const openFeedbackForSocialBtn = document.getElementById('openFeedbackForSocialBtn');

    async function copyWithFallback(text, fallbackElement) {
        const t = (text || '').toString();
        if (!t) return false;
        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(t);
                return true;
            }
        } catch (e) {}
        try {
            if (fallbackElement && typeof fallbackElement.select === 'function') {
                const prev = fallbackElement.readOnly;
                try { fallbackElement.readOnly = false; } catch (e) {}
                fallbackElement.focus();
                fallbackElement.select();
                const ok = document.execCommand && document.execCommand('copy');
                try { fallbackElement.setSelectionRange(0, 0); } catch (e) {}
                try { fallbackElement.blur(); } catch (e) {}
                try { fallbackElement.readOnly = prev; } catch (e) {}
                if (ok) return true;
            }
        } catch (e) {}
        try {
            const ta = document.createElement('textarea');
            ta.value = t;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            ta.style.top = '0';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            const ok = document.execCommand && document.execCommand('copy');
            document.body.removeChild(ta);
            return !!ok;
        } catch (e) { return false; }
    }

    if (generateSocialCopyBtn && socialCopyText) {
        generateSocialCopyBtn.addEventListener('click', async () => {
            try {
                generateSocialCopyBtn.disabled = true;
                generateSocialCopyBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 生成中...';
                // 优先读取当前正在进行的任务名称
                let currentTaskName = '';
                try {
                    const taskNameDisplayEl = document.getElementById('taskNameDisplay');
                    const nameText = taskNameDisplayEl && taskNameDisplayEl.textContent ? taskNameDisplayEl.textContent.trim() : '';
                    if (nameText && nameText !== '未命名任务') currentTaskName = nameText;
                } catch (e) {}

                const payload = { };
                if (currentTaskName) payload.current_task_name = currentTaskName;

                const data = await fetchAPI(ENDPOINTS.socialShareCopy, { method: 'POST', body: JSON.stringify(payload) });
                
                if (!data.success) {
                    showToast(data.message || '生成失败', 'error');
                } else {
                    socialCopyText.value = data.copy || '';
                    if (!data.copy) showToast('未生成文案，请稍后再试', 'warning');
                }
            } catch (e) {
                showToast('生成失败，请检查网络', 'error');
            } finally {
                generateSocialCopyBtn.disabled = false;
                generateSocialCopyBtn.innerHTML = '<i class="bi bi-stars"></i> 生成文案';
            }
        });
    }

    if (copySocialCopyBtn && socialCopyText) {
        copySocialCopyBtn.addEventListener('click', async () => {
            const ok = await copyWithFallback(socialCopyText.value || '', socialCopyText);
            showToast(ok ? '文案已复制' : '复制失败，请手动选择复制', ok ? 'success' : 'error');
        });
    }

    if (openFeedbackForSocialBtn && socialCopyText) {
        openFeedbackForSocialBtn.addEventListener('click', () => {
            // 预填反馈类别与引导描述
            const cat = 'social_share';
            const guide = '请上传社交平台传播的截图（含粉丝量、浏览量、收藏/转发等数据）；可在下方附上链接或说明。\n\n以下为本次传播文案（可修改）：\n\n' + (socialCopyText.value || '');
            if (feedbackCategoryInput) feedbackCategoryInput.value = cat;
            if (feedbackMetadataInput) feedbackMetadataInput.value = JSON.stringify({ type: 'social', from: 'free_points_modal' });
            if (feedbackDescription) feedbackDescription.value = guide;
            const modal = new bootstrap.Modal(document.getElementById('feedbackModal'));
            modal.show();
        });
    }
    
    // 逐条查看与校准
    const viewDetailsBtn = document.getElementById('viewDetailsSequentiallyBtn');
    if (viewDetailsBtn) {
        viewDetailsBtn.addEventListener('click', () => {
            const detailedSection = document.getElementById('detailedReviewSection');
            if (detailedSection) {
                detailedSection.style.display = 'block';
                try { detailedSection.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (e) {}
            }

            // 确保单条校准地图存在
            const itemMapEl = document.getElementById('itemCalibrationMap');
            const mapNeedsInit = !window.itemCalibrationMap || typeof window.itemCalibrationMap.setView !== 'function';
            if (itemMapEl && mapNeedsInit) {
                window.itemCalibrationMap = initializeMap('itemCalibrationMap');
                setTimeout(() => window.itemCalibrationMap && window.itemCalibrationMap.invalidateSize && window.itemCalibrationMap.invalidateSize(), 120);
            }

            // 确保校准面板存在并设置地图
            if (!window.calibrationPanel) {
                window.calibrationPanel = initializeCalibrationPanel(
                    window.itemCalibrationMap,
                    {
                        onResultChanged: (updatedRow, index) => {
                            if (Array.isArray(window.currentResults)) {
                                window.currentResults[index] = updatedRow;
                                updateResultsTable(window.currentResults, { scroll: false });
                                updateResultsOverview();
                            }
                        }
                    },
                    window.currentUser
                );
            } else {
                if (window.itemCalibrationMap && window.calibrationPanel.setMap) {
                    window.calibrationPanel.setMap(window.itemCalibrationMap);
                }
            }

            // 绑定一次性的面板内部按钮事件（若未绑定）
            if (!window.__calibrationControlsBound) {
                window.__calibrationControlsBound = true;
                document.addEventListener('click', (e) => {
                    // 上一个（循环切换）
                    const prevBtn = e.target.closest('.prev-result-btn');
                    if (prevBtn && window.calibrationPanel && Array.isArray(window.currentResults)) {
                        e.preventDefault();
                        const currentIndex = window.calibrationPanel.isShowingResult ? window.currentResults.findIndex((_, i) => window.calibrationPanel.isShowingResult(i)) : 0;
                        const len = window.currentResults.length;
                        const newIndex = ((currentIndex - 1) + len) % len;
                        window.calibrationPanel.showPanelFor(window.currentResults[newIndex], newIndex, window.currentResults.length);
                        return;
                    }
                    // 下一个（循环切换）
                    const nextBtn = e.target.closest('.next-result-btn');
                    if (nextBtn && window.calibrationPanel && Array.isArray(window.currentResults)) {
                        e.preventDefault();
                        const currentIndex = window.calibrationPanel.isShowingResult ? window.currentResults.findIndex((_, i) => window.calibrationPanel.isShowingResult(i)) : 0;
                        const len = window.currentResults.length;
                        const newIndex = (currentIndex + 1) % len;
                        window.calibrationPanel.showPanelFor(window.currentResults[newIndex], newIndex, window.currentResults.length);
                        return;
                    }
                    // 手动标注
                    const manualBtn = e.target.closest('#manualMarkBtnOnMap');
                    if (manualBtn && window.calibrationPanel && window.calibrationPanel.toggleManualMarkMode) {
                        e.preventDefault();
                        window.calibrationPanel.toggleManualMarkMode();
                        return;
                    }
                    // 地址查找工具
                    const showToolsBtn = e.target.closest('#showAddressSearchToolsBtn');
                    if (showToolsBtn) {
                        e.preventDefault();
                        const tools = document.getElementById('addressSearchToolsContainer');
                        if (tools) {
                            tools.style.display = 'block';
                            try { tools.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (e) {}
                        }
                        return;
                    }
                });
            }

            if (window.calibrationPanel && Array.isArray(window.currentResults) && window.currentResults.length > 0) {
                window.calibrationPanel.showPanelFor(window.currentResults[0], 0, window.currentResults.length);
            } else {
            }
        });
    }

    // 初始化POI地图搜索
    const poiMap = ensureCalibrationMap('itemCalibrationMap');
    if (poiMap) {
        initializeMapSearch(poiMap, (selectedPoi) => {
            // console.log('[DEBUG] 6. onPoiSelected回调函数在script.js中被触发，接收到选择的POI:', selectedPoi);
            if (window.calibrationPanel) {
                const allPoiResults = getPoiResults();
                const selectedIndex = allPoiResults.findIndex(poi => poi === selectedPoi);
                // console.log('[DEBUG] 7. 在当前POI列表中重新计算选中项的索引，结果为:', selectedIndex);

                if (selectedIndex !== -1) {
                    if (window.calibrationPanel.setMapSearchResults) {
                        window.calibrationPanel.setMapSearchResults(allPoiResults);
                    }
                    // console.log('[DEBUG] 8. 准备调用校准面板的handleMapPoiSelection方法来更新UI。');
                    window.calibrationPanel.handleMapPoiSelection(selectedIndex, '地址查找工具选定');
                } else {
                    // console.log('[DEBUG] 8a. 错误：接收到的POI在当前列表中找不到，无法更新UI。');
                    showToast('在结果列表中未找到选定的POI', 'error');
                }
            }
        });
    }

    // 显示全部（总览地图缩放到所有标注）
    const showAllBtn = document.getElementById('showAllOnOverviewMapBtn');
    if (showAllBtn) {
        showAllBtn.addEventListener('click', () => {
            const map = ensureResultsOverviewMap('map');
            if (!map) return;
            const selectedResults = Array.isArray(window.currentResults)
                ? window.currentResults.filter(item => item && item.selected_result)
                : [];
            if (selectedResults.length === 0) return;
            // 计算边界并缩放
            const latlngs = [];
            selectedResults.forEach(item => {
                const r = item.selected_result.result || {};
                const lat = r.latitude_gcj02 || r.latitude_wgs84;
                const lng = r.longitude_gcj02 || r.longitude_wgs84;
                if (typeof lat === 'number' && typeof lng === 'number') latlngs.push([lat, lng]);
            });
            if (latlngs.length > 0) {
                try { map.fitBounds(latlngs, { padding: [40, 40], maxZoom: 16 }); } catch (e) {}
            }
        });
    }
    
    // 退出登录按钮
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            handleLogout();
        });
    }

    // 智能选点按钮
    const smartSelectPointBtn = document.getElementById('smartSelectPointBtn');
    if (smartSelectPointBtn) {
        smartSelectPointBtn.addEventListener('click', () => {
            if (!checkUserPoints()) return;
            handleAutoSelect();
        });
    }

    // 智能校准按钮
    const smartCalibrationBtn = document.getElementById('smartCalibrationBtn');
    if (smartCalibrationBtn) {
        smartCalibrationBtn.addEventListener('click', () => {
            if (!checkUserPoints()) return;
            startSmartCalibration();
        });
    }

    // 导出文件按钮与确认流程
    const exportExcelBtn = document.getElementById('exportExcelBtn');
    const exportKmlBtn = document.getElementById('exportKmlBtn');
    const exportShpBtn = document.getElementById('exportShpBtn');
    const confirmExportBtn = document.getElementById('confirmExportBtn');
    const exportRecordCount = document.getElementById('exportRecordCount');
    const exportTaskNameInput = document.getElementById('exportTaskName');
    const exportConfirmModalEl = document.getElementById('exportConfirmModal');
    let selectedExportFormat = null; // 'xlsx' | 'kml' | 'shp'

    function openExportModal(forFormat) {
        selectedExportFormat = forFormat;
        // 统计已选定记录数
        const selected = Array.isArray(window.currentResults)
            ? window.currentResults.filter(item => item && item.selected_result)
            : [];
        if (exportRecordCount) exportRecordCount.textContent = String(selected.length || 0);
        // 预填任务名称
        try {
            const taskNameDisplay = document.getElementById('taskNameDisplay');
            const fallback = '地理编码结果';
            const text = (taskNameDisplay && taskNameDisplay.textContent && taskNameDisplay.textContent.trim()) || fallback;
            if (exportTaskNameInput && !exportTaskNameInput.value) exportTaskNameInput.value = text;
        } catch (e) {}
        // 打开模态框
        try {
            const modal = new bootstrap.Modal(exportConfirmModalEl);
            modal.show();
        } catch (e) {
            showToast('无法打开导出确认窗口', 'error');
        }
    }

    function buildExportPayload() {
        const selected = Array.isArray(window.currentResults)
            ? window.currentResults.filter(item => item && item.selected_result)
            : [];
        if (selected.length === 0) return [];

        // 将所选结果映射为后端期望的结构（至少包含 lng/lat 为 WGS84）
        const rows = [];
        for (const item of selected) {
            try {
                const sel = item.selected_result || {};
                const r = sel.result || {};
                let lng = typeof r.longitude_wgs84 === 'number' ? r.longitude_wgs84 : undefined;
                let lat = typeof r.latitude_wgs84 === 'number' ? r.latitude_wgs84 : undefined;
                if ((typeof lng !== 'number' || typeof lat !== 'number') &&
                    typeof r.longitude_gcj02 === 'number' && typeof r.latitude_gcj02 === 'number') {
                    const conv = convertCoordinates(r.longitude_gcj02, r.latitude_gcj02, 'GCJ02', 'WGS84');
                    lng = conv && typeof conv.longitude === 'number' ? conv.longitude : lng;
                    lat = conv && typeof conv.latitude === 'number' ? conv.latitude : lat;
                }
                if (typeof lng !== 'number' || typeof lat !== 'number') continue; // 跳过无坐标的

                rows.push({
                    address: item.address || '',
                    name: r.name || r.formatted_address || '',
                    province: r.province || '',
                    city: r.city || '',
                    district: r.district || r.county || '',
                    lng: lng,
                    lat: lat,
                    api: sel.api || sel.source_api || '',
                    confidence: typeof sel.confidence === 'number' ? sel.confidence : undefined,
                    llm_reason: sel.llm_reason || sel.selection_method_note || ''
                });
            } catch (e) { /* 忽略单行错误 */ }
        }
        return rows;
    }

    async function handleConfirmExport() {
        if (!checkUserPoints()) return;

        try {
            if (!selectedExportFormat) {
                showToast('未选择导出格式', 'warning');
                return;
            }
            const data = buildExportPayload();
            if (!data || data.length === 0) {
                showToast('没有可导出的“已选定”记录', 'warning');
                return;
            }
            const locationNameRaw = exportTaskNameInput && exportTaskNameInput.value ? exportTaskNameInput.value.trim() : 'geocoding_results';
            const safeName = locationNameRaw.replace(/[\\/:*?"<>|]+/g, '_');

            // 发送请求
            const { blob, points } = await exportData(selectedExportFormat, data, safeName);
            
            // 如果返回了新的积分，则更新UI
            if (points !== null && !isNaN(points)) {
                if (window.currentUser) {
                    window.currentUser.points = points;
                }
                updateUserBar({ ...window.currentUser, points: points });
            }

            // 生成文件名
            const extMap = { xlsx: 'xlsx', kml: 'kml', shp: 'zip' };
            const ext = extMap[selectedExportFormat] || 'dat';
            const fileName = `${safeName}.${ext}`;

            // 触发下载
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = fileName;
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }, 0);

            showToast('导出任务完成，已开始下载', 'success');
            // 关闭模态
            try {
                const modal = bootstrap.Modal.getInstance(exportConfirmModalEl) || new bootstrap.Modal(exportConfirmModalEl);
                modal.hide();
            } catch (e) {}
        } catch (err) {
            showToast(`导出失败: ${err.message || err}`, 'error');
        }
    }

    if (confirmExportBtn) {
        confirmExportBtn.addEventListener('click', handleConfirmExport);
    }
    if (exportExcelBtn) {
        exportExcelBtn.addEventListener('click', (e) => {
            e.preventDefault();
            openExportModal('xlsx');
        });
    }
    if (exportKmlBtn) {
        exportKmlBtn.addEventListener('click', (e) => {
            e.preventDefault();
            openExportModal('kml');
        });
    }
    if (exportShpBtn) {
        exportShpBtn.addEventListener('click', (e) => {
            e.preventDefault();
            openExportModal('shp');
        });
    }
}

// 地理编码处理
async function handleGeocode(mode) {
    
    const geocodingTip = document.getElementById('geocoding-tip');
    const textarea = document.getElementById('addresses');
    
    // 检查地址行数并显示提示
    if (textarea && geocodingTip) {
        const lines = textarea.value.trim().split('\n').filter(line => line.trim() !== '');
        if (lines.length === 1) {
            geocodingTip.textContent = '小提示：您可以一次粘贴多个地址进行批量处理哦！';
            geocodingTip.style.display = 'block';
        } else {
            geocodingTip.style.display = 'none';
        }
    }

    // 先主动检查最新用户登录状态
    await checkUserLoginStatus();
    
    // 尝试多种方式获取用户状态
    let user = window.currentUser;
    if (!user && typeof currentUser !== 'undefined') {
        user = currentUser;
        window.currentUser = currentUser; // 同步到 window.currentUser
    }
    
    if (!user) {
        showToast('请先登录后开始使用', 'warning');
        // 设置登录后要执行的动作
        window.actionAfterLogin = () => handleGeocode(mode);
        // 显示登录模态框
        showLoginModal();
        return;
    }
    
    if (!textarea || !textarea.value.trim()) {
        showToast('请输入地址', 'warning');
        if (geocodingTip) geocodingTip.style.display = 'none'; // 如果没有输入，也隐藏提示
        return;
    }
    
    try {
        // 获取地址输入模块的状态
        const addressInputModule = window.addressInputModule;
        if (!addressInputModule) {
            showToast('地址输入模块未正确初始化', 'error');
            return;
        }
        
        // 新增：在地理编码前，自动执行地址补全
        showToast('正在自动补全行政区划...', 'info');
        await addressInputModule.autoCompleteAddresses();
        showToast('行政区划补全完成，开始地理编码...', 'info');

        // 获取结果地图实例（如果存在）
        const resultsOverviewMap = window.resultsOverviewMap || null;
        
        // 调用地理编码处理函数
        const isSmartMode = mode === 'smart';
        
        const result = await handleGeocodeClick(addressInputModule, resultsOverviewMap, isSmartMode);
        
        if (result) {
            showToast('地理编码完成', 'success');
        } else {
        }
        
    } catch (error) {
        showToast('地理编码处理失败: ' + error.message, 'error');
        if (geocodingTip) geocodingTip.style.display = 'none'; // 出错时隐藏提示
    }
}

// 检查用户登录状态（调用后端API）
async function checkUserLoginStatus() {
    try {
        const response = await fetch('/check_login_status');
        const data = await response.json();
        
        if (data.logged_in && data.user) {
            window.currentUser = data.user;
            // 同步到HTML变量（如果存在）
            if (typeof currentUser !== 'undefined') {
                currentUser = data.user;
            }
            updateUserBar(data.user);
        } else {
            window.currentUser = null;
            if (typeof currentUser !== 'undefined') {
                currentUser = null;
            }
            updateUserBar(null);
        }
    } catch (error) {
        window.currentUser = null;
        if (typeof currentUser !== 'undefined') {
            currentUser = null;
        }
    }
}

// 设置当前用户
function setCurrentUserGlobal(user) {
    window.currentUser = user; // 更新全局 currentUser
    updateUserBar(user);
    // 重新初始化features模块以传递新的用户信息
    if (user) {
        initializeFeatures(user);
    }
}

// 添加定期同步用户状态的机制
function syncUserStatus() {
    // 如果HTML中有currentUser但window.currentUser为空，则同步
    if (typeof currentUser !== 'undefined' && currentUser && !window.currentUser) {
        window.currentUser = currentUser;
        updateUserBar(currentUser);
    }
}

// 立即执行一次同步
syncUserStatus();

// 定期检查用户状态同步（每3秒检查一次，避免频繁日志）
setInterval(syncUserStatus, 3000);

// 退出登录处理
async function handleLogout() {
    try {
        const response = await fetch('/logout');
        
        if (response.ok) {
            // 清除用户状态
            setCurrentUserGlobal(null);
            showToast('已退出登录', 'success');
            // 刷新页面
            window.location.reload();
        } else {
            showToast('退出登录失败', 'error');
        }
    } catch (error) {
        showToast('退出登录失败', 'error');
    }
}

// 统一的页面初始化函数
let hasInitialized = false;

async function initializePage() {
    if (hasInitialized) {
        return;
    }
    
    hasInitialized = true;
    
    // 首先同步用户状态
    syncUserStatus();
    // 紧接着从后端确认一次登录状态，确保刷新后保持登录
    await checkUserLoginStatus();
    
    // 初始化认证功能
    initializeAuthForms();

    // 未登录情况下，暂存URL中的推荐码，等待登录后绑定
    try {
        const params = new URLSearchParams(window.location.search || '');
        const code = (params.get('ref') || '').trim();
        if (code) {
            localStorage.setItem('pending_referral_code', code);
        }
    } catch (e) {}

    // 初始化通知模块（需用户状态，但也可先加载未读数）
    try { initializeNotifications(); } catch (e) {}

    // 初始化任务管理器
    initializeTaskManager();
    
    // 预初始化校准面板以支持状态管理
    try {
        if (!window.calibrationPanel) {
            // 创建一个临时的地图实例用于初始化
            const tempMap = null; // 后续会在实际使用时设置
            window.calibrationPanel = initializeCalibrationPanel(
                tempMap,
                {
                    onResultChanged: (updatedRow, index) => {
                        if (Array.isArray(window.currentResults)) {
                            window.currentResults[index] = updatedRow;
                            if (window.updateResultsTable) {
                                window.updateResultsTable(window.currentResults, { scroll: false });
                            }
                            if (window.updateResultsOverview) {
                                window.updateResultsOverview();
                            }
                        }
                    }
                },
                window.currentUser
            );
        }
    } catch (e) {
    }
    
    // 初始化地址处理模块
    
    // 先检查必要的DOM元素是否存在
    const addressesElement = document.getElementById('addresses');
    const autoCompleteBtn = document.getElementById('autoCompleteBtn');
    const autoSplitBtn = document.getElementById('autoSplitBtn');
    const normalGeocodeBtn = document.getElementById('normalGeocodeBtn');
    const smartGeocodeBtn = document.getElementById('smartGeocodeBtn');
    
    initializeAddressCleaner();
    
    // 初始化地址输入模块并保存到全局作用域
    const addressInputModule = initializeAddressInput();
    window.addressInputModule = addressInputModule;
    
    // 添加测试函数到全局作用域以便调试
    window.testAddressCleaning = function() {
        const textarea = document.getElementById('addresses');
        if (textarea) {
            const testData = '1. 北京市海淀区\n2. 上海市浦东新区\n   3. 广州市天河区   \n';
            textarea.value = testData;
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
        } else {
        }
    };
    
    // 添加地理编码测试函数
    window.testGeocoding = function(mode = 'normal') {
        const textarea = document.getElementById('addresses');
        if (textarea && !textarea.value.trim()) {
            const testData = '北京市海淀区中关村创业大街\n上海市浦东新区世纪大道88号';
            textarea.value = testData;
        }
        handleGeocode(mode);
    };
    
    // 添加用户状态调试函数
    window.debugUserStatus = async function() {
        
        // 尝试强制同步
        syncUserStatus();
        
        // 主动检查后端状态
        await checkUserLoginStatus();
    };
    
    // 添加DOM元素检查函数
    window.debugDOMElements = function() {
        
        const elements = {
            'addresses': document.getElementById('addresses'),
            'cascadeResultsBody': document.getElementById('cascadeResultsBody'),
            'cascadeResultsContainer': document.querySelector('#cascadeResultsContainer'),
            'batchResultsLoadingOverlay': document.getElementById('batchResultsLoadingOverlay'),
            'normalGeocodeBtn': document.getElementById('normalGeocodeBtn'),
            'smartGeocodeBtn': document.getElementById('smartGeocodeBtn'),
            'autoCompleteBtn': document.getElementById('autoCompleteBtn'),
            'autoSplitBtn': document.getElementById('autoSplitBtn')
        };
        
        for (const [name, element] of Object.entries(elements)) {
            if (element) {
                if (element.style && element.style.display) {
                }
            } else {
            }
        }
    };

    // 设置全局点击处理器
    window.globalCascadeClickHandler = handleCascadeTableClick;
    
    // 初始化地图函数
    const mapContainer = document.getElementById('map');
    if (mapContainer) {
        window.initializeMapGlobal = ensureResultsOverviewMap;
    }
    
    // 初始化搜索表单
    const searchForm = document.getElementById('smartSearchForm');
    if (searchForm) {
        searchForm.addEventListener('submit', handleSmartSearch);
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
        }
    }

    // 初始化结果分页控件
    try {
        const pageSizeSelect = document.getElementById('resultsPageSize');
        const paginationUl = document.getElementById('resultsPagination');
        if (pageSizeSelect && paginationUl) {
            pageSizeSelect.value = String(__resultsPerPage);
            pageSizeSelect.addEventListener('change', () => {
                const newSize = parseInt(pageSizeSelect.value, 10) || 15;
                __resultsPerPage = newSize;
                __resultsPage = 1;
                if (Array.isArray(window.currentResults)) {
                    renderResultsWithPagination(window.currentResults);
                }
            });
        }
    } catch (e) {}
    
    // 初始化地图（仅当容器已有非零尺寸时）
    try {
        const mapEl = document.getElementById('map');
        const rect = mapEl ? mapEl.getBoundingClientRect() : { width: 0, height: 0 };
        if (typeof window.initializeMapGlobal === 'function' && rect.width > 0 && rect.height > 0) {
            const mapInstance = window.initializeMapGlobal('map'); // ensure 版本
            window.resultsOverviewMap = mapInstance;
            if (mapInstance && typeof mapInstance.invalidateSize === 'function') {
                setTimeout(() => mapInstance.invalidateSize(), 100);
            }
        } else {
        }
    } catch (e) {
    }
    
    // 初始化API选择
    const cascadeApi = document.getElementById('cascadeApi');
    if (cascadeApi) {
        cascadeApi.addEventListener('change', function() {
            if (this.checked) {
            }
        });
    }
    
    // 初始化特性功能
    initializeFeatures(window.currentUser);
    
    // 调用页面特性初始化函数
    if (typeof window.initializePageSpecificFeatures === 'function') {
        try {
            window.initializePageSpecificFeatures();
        } catch (error) {
        }
    } else {
    }
    
}

// 包装函数用于任务管理器
function updateResultsTable(data, options = {}) {
    const container = document.querySelector(SELECTORS.resultsContainer);
    if (container) {
        const prevDisplay = container.style.display;
        container.style.display = 'block';
        // 一旦容器可见，确保/创建地图
        try {
            const map = ensureResultsOverviewMap('map');
            if (map) {
                window.resultsOverviewMap = map;
            }
        } catch (e) { }
    } else {
    }

    // 保存到全局并按分页渲染
    try { window.currentResults = Array.isArray(data) ? data : []; } catch (e) {}
    renderResultsWithPagination(window.currentResults, options);

    // 渲染完成后的调试信息
    const tbody = document.querySelector(SELECTORS.resultsTbody);
    const rows = tbody ? tbody.querySelectorAll('tr').length : 0;
    if (container && options.scroll !== false) {
        try {
            container.scrollIntoView({ behavior: 'smooth' });
        } catch (e) {
        }
    }
    // 渲染后尝试更新总览地图标记
    try { updateResultsOverview(); } catch (e) { }

    // 渲染后：如果“逐条校准区”已打开，则自动同步到当前项或第一条
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
    }

    // 分发一个自定义事件，供其他模块监听结果表变化
    try {
        const evt = new CustomEvent('cascadeResultsUpdated', { detail: { results: data } });
        document.dispatchEvent(evt);
    } catch (e) {
        // 忽略老旧浏览器环境的事件构造失败
    }
}

function renderResultsWithPagination(allData, options = {}) {
    const tbody = document.querySelector(SELECTORS.resultsTbody);
    const paginationUl = document.getElementById('resultsPagination');
    const pageSizeSelect = document.getElementById('resultsPageSize');
    if (!tbody) return;

    const total = Array.isArray(allData) ? allData.length : 0;
    const perPage = __resultsPerPage > 0 ? __resultsPerPage : 15;
    const totalPages = Math.max(1, Math.ceil(total / perPage));
    if (__resultsPage > totalPages) __resultsPage = totalPages;
    if (__resultsPage < 1) __resultsPage = 1;
    const start = ( __resultsPage - 1 ) * perPage;
    const end = start + perPage;
    const pageData = Array.isArray(allData) ? allData.slice(start, end) : [];

    const indexOffset = start;
    if (typeof window.displayCascadeResults === 'function') {
        window.displayCascadeResults(tbody, pageData, -1, indexOffset);
    } else if (typeof displayCascadeResults === 'function') {
        displayCascadeResults(tbody, pageData, -1, indexOffset);
    }

    // 构建分页条
    if (paginationUl) {
        const isPrevDisabled = __resultsPage <= 1;
        const isNextDisabled = __resultsPage >= totalPages;
        const makeLi = (label, disabled, handlerClass, ariaLabel) => `
            <li class="page-item ${disabled ? 'disabled' : ''}">
                <a class="page-link ${handlerClass}" href="#" aria-label="${ariaLabel || label}">${label}</a>
            </li>`;

        // 简洁起见：上一页、当前页/总页、下一页
        paginationUl.innerHTML =
            makeLi('&laquo;', isPrevDisabled, 'results-prev-page', 'Previous') +
            `<li class="page-item disabled"><span class="page-link">${__resultsPage} / ${totalPages}</span></li>` +
            makeLi('&raquo;', isNextDisabled, 'results-next-page', 'Next');

        paginationUl.querySelector('.results-prev-page')?.addEventListener('click', (e) => {
            e.preventDefault();
            if (__resultsPage > 1) {
                __resultsPage -= 1;
                renderResultsWithPagination(allData, options);
            }
        });
        paginationUl.querySelector('.results-next-page')?.addEventListener('click', (e) => {
            e.preventDefault();
            if (__resultsPage < totalPages) {
                __resultsPage += 1;
                renderResultsWithPagination(allData, options);
            }
        });

        if (pageSizeSelect) {
            pageSizeSelect.value = String(perPage);
        }
    }
}

function updateResultsOverview() {
    const map = ensureResultsOverviewMap('map');
    if (!map) {
        return;
    }
    const selectedResults = Array.isArray(window.currentResults)
        ? window.currentResults.filter(item => item && item.selected_result)
        : [];
    updateResultsOverviewMapMarkers(map, selectedResults);
}

function updateStats() {
    // 这是一个占位符函数，如果需要更新统计信息，可以在这里实现
}

// 暴露全局函数
window.initialize = initializePage;
window.initializePageSpecificFeatures = initializePageSpecificFeatures;
window.setCurrentUser = setCurrentUserGlobal;
window.updateResultsTable = updateResultsTable;

window.updateResultsOverview = updateResultsOverview;
window.updateStats = updateStats;

// 新增：从结果列表直接跳转到逐条校准视图的指定条目
window.showItemInDetailedView = function(rowIndex) {
    const detailedSection = document.getElementById('detailedReviewSection');
    const viewDetailsBtn = document.getElementById('viewDetailsSequentiallyBtn');

    if (!detailedSection || !viewDetailsBtn) {
        showToast('无法打开逐条校准界面', 'error');
        return;
    }

    const isDetailedViewVisible = detailedSection.style.display !== 'none';

    // 如果逐条查看界面未展开，则先模拟点击按钮以展开并完成所有初始化
    if (!isDetailedViewVisible) {
        viewDetailsBtn.click();
    }

    // 使用一个短延迟以确保在视图展开和初始化后执行
    // 如果视图已经是打开的，这也提供了一个平滑的导航体验
    setTimeout(() => {
        if (window.calibrationPanel && typeof window.calibrationPanel.showPanelFor === 'function' && Array.isArray(window.currentResults) && window.currentResults[rowIndex]) {
            // 调用校准面板的核心方法来显示指定索引的结果
            window.calibrationPanel.showPanelFor(window.currentResults[rowIndex], rowIndex, window.currentResults.length);
            
            // 滚动到逐条校准区
            if (detailedSection.scrollIntoView) {
                detailedSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        } else {
            showToast(`无法导航到条目 ${rowIndex + 1}`, 'warning');
        }
    }, isDetailedViewVisible ? 0 : 200); // 如果已可见，立即执行；如果不可见，等待初始化
};

// 新增：切换批量结果某行的“已确认”状态
window.toggleRowConfirmation = function(rowIndex) {
    try {
        if (!Array.isArray(window.currentResults) || !window.currentResults[rowIndex]) return;
        const row = window.currentResults[rowIndex];
        row.confirmed = !row.confirmed;

        try { showToast(row.confirmed ? '已确认' : '已取消确认', 'success'); } catch (e) {}

        if (typeof window.updateResultsTable === 'function') {
            window.updateResultsTable(window.currentResults, { scroll: false });
        } else if (typeof displayCascadeResults === 'function') {
            const tbody = document.querySelector(SELECTORS.resultsTbody);
            if (tbody) {
                const perPage = __resultsPerPage > 0 ? __resultsPerPage : 15;
                const pageIndex = Math.floor(rowIndex / perPage) + 1;
                __resultsPage = pageIndex;
                const start = ( __resultsPage - 1 ) * perPage;
                const pageData = Array.isArray(window.currentResults) ? window.currentResults.slice(start, start + perPage) : [];
                displayCascadeResults(tbody, pageData, rowIndex, start);
            }
        }

        try { window.updateResultsOverview && window.updateResultsOverview(); } catch (e) {}

        try {
            const detailedSection = document.getElementById('detailedReviewSection');
            const isOpen = detailedSection && detailedSection.style.display !== 'none';
            if (isOpen && window.calibrationPanel && typeof window.calibrationPanel.showPanelFor === 'function') {
                window.calibrationPanel.showPanelFor(window.currentResults[rowIndex], rowIndex, window.currentResults.length);
            }
        } catch (e) {}
    } catch (e) {}
};

// 确保只在 DOMContentLoaded 时初始化一次
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializePage);
} else {
    // 如果 DOMContentLoaded 已经触发，直接初始化
    initializePage();
}
