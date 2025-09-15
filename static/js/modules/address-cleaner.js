import { createAndAppendElement } from './utils.js';

/**
 * 地址清理工具
 * 用于清理地址列表，去除序号、缩进、空格和空行
 */

// 清理地址列表函数
export function cleanAddresses(text) {
    // console.log('🧹 开始清理地址，输入长度:', text ? text.length : 0);
    if (!text) {
        // console.log('🧹 输入为空，返回空字符串');
        return '';
    }

    // 使用更健壮的正则表达式来分割行，以处理不同的换行符（CRLF, LF）
    let lines = text.split(/\r?\n|\r/);
    // console.log('🧹 分割后行数:', lines.length);
    
    let cleanedLines = lines.map((line, index) => {
        // console.log(`🧹 处理第${index + 1}行: "${line}"`);
        
        // 1. 去除首尾的空白字符
        let processedLine = line.trim();
        // console.log(`  去空格后: "${processedLine}"`);
        
        // 2. 移除行首的各种列表标记（数字、符号等）
        // V2.0 SOP中的核心正则表达式，保持不变
        const beforeMarkerRemoval = processedLine;
        processedLine = processedLine.replace(/^\s*([【（(\[#*•-]|\d+[.)、．\]】])\s*/, '');
        if (beforeMarkerRemoval !== processedLine) {
            // console.log(`  移除标记后: "${processedLine}"`);
        }
        
        // 3. 将全角空格替换为半角空格，然后将多个连续的空白符合并为单个空格，最后再次trim
        // 这是为了标准化地址内部的空格，而不是完全移除它们
        const beforeSpaceNormalization = processedLine;
        processedLine = processedLine.replace(/　/g, ' ').replace(/\s+/g, ' ').trim();
        if (beforeSpaceNormalization !== processedLine) {
            // console.log(`  空格标准化后: "${processedLine}"`);
        }
        
        // 4. 过滤掉清理后只剩下无关符号或纯数字的"垃圾行"
        if (/^[^\w\u4e00-\u9fa5]+$/.test(processedLine)) {
            // console.log(`  垃圾行(符号): "${processedLine}" - 过滤`);
            return '';
        }
        if (/^\d*$/.test(processedLine)) {
            // console.log(`  垃圾行(数字): "${processedLine}" - 过滤`);
            return '';
        }
        if (/^\(?\d+\)?$/.test(processedLine) || /^（\d+）$/.test(processedLine)) {
            // console.log(`  垃圾行(括号数字): "${processedLine}" - 过滤`);
            return '';
        }
        
        // console.log(`  最终结果: "${processedLine}"`);
        return processedLine;
    });
    
    // 5. 过滤掉所有处理后变为空的行，并用换行符重新组合
    const result = cleanedLines.filter(line => line).join('\n');
    // console.log('🧹 清理完成，有效行数:', cleanedLines.filter(line => line).length);
    // console.log('🧹 最终结果:', result.substring(0, 200) + (result.length > 200 ? '...' : ''));
    return result;
}

// 存储从数据库获取的后缀列表
let databaseSuffixes = [];

// 从服务器获取地名类型后缀列表
async function fetchLocationTypeSuffixes() {
    try {
        const response = await fetch('/get_location_types');
        const data = await response.json();
        if (data.success && Array.isArray(data.types)) {
            // 更新后缀列表，按长度倒序排列（先检查长的后缀）
            databaseSuffixes = data.types.sort((a, b) => b.length - a.length);
            return databaseSuffixes;
        }
    } catch (error) {
        console.error('获取地名类型后缀失败:', error);
    }
    return [];
}

// 检测地址列表中的后缀，并自动生成标签
export async function detectCommonSuffix(addresses) {
    if (!addresses || addresses.length === 0) return;

    // 确保我们有最新的后缀列表
    if (databaseSuffixes.length === 0) {
        await fetchLocationTypeSuffixes();
    }

    // 如果数据库中没有后缀，使用默认的常见后缀
    let suffixesToCheck = databaseSuffixes;
    if (suffixesToCheck.length === 0) {
        suffixesToCheck = [
            "历史文化街区", "农业科技园区", "经济技术开发区", "高新技术产业开发区", 
            "产业园区", "国家公园", "风景名胜区", "自然保护区", "示范区", 
            "工业园区", "文化街区", "开发区", "商业区", "科技园", "公园", 
            "校区", "景区", "园区", "街区"
        ];
    }

    // 检查每个地址的后缀
    const foundSuffixes = new Set();
    for (const address of addresses) {
        for (const suffix of suffixesToCheck) {
            if (address.endsWith(suffix)) {
                foundSuffixes.add(suffix);
            }
        }
    }

    // 添加找到的后缀作为标签
    foundSuffixes.forEach(suffix => {
        // 直接分发事件，让 address-input 模块全权负责UI更新
        const event = new CustomEvent('locationTypeTagAdded', { detail: { tag: suffix } });
        document.dispatchEvent(event);
    });
}

// 保存新的地名类型后缀到数据库
export async function saveLocationTypeSuffix(suffix) {
    if (!suffix) return;
    
    try {
        const response = await fetch('/save_location_type', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ type: suffix })
        });
        
        const data = await response.json();
        if (data.success) {
            // 如果保存成功且不在当前列表中，添加到列表
            if (!databaseSuffixes.includes(suffix)) {
                databaseSuffixes.push(suffix);
                // 重新排序
                databaseSuffixes.sort((a, b) => b.length - a.length);
            }
        }
    } catch (error) {
        console.error('保存地名类型后缀失败:', error);
    }
}

// 显示地址格式已清除的提示
function showCleanNotification(textarea) {
    // 检查是否已经存在提示元素
    const existingNotification = document.getElementById('clean-notification');
    if (existingNotification) {
        // 重置计时器
        clearTimeout(existingNotification.timer);
        existingNotification.timer = setTimeout(() => {
            existingNotification.style.opacity = '0';
            setTimeout(() => {
                if (existingNotification.parentNode) {
                    existingNotification.parentNode.removeChild(existingNotification);
                }
            }, 500);
        }, 3000);
        return;
    }
    
    // 创建提示元素
    const container = textarea.parentNode;
    container.style.position = 'relative';
    const notification = createAndAppendElement('div', {
        id: 'clean-notification',
        styles: {
            position: 'absolute',
            bottom: '5px',
            right: '10px',
            backgroundColor: 'rgba(0, 123, 255, 0.1)',
            color: '#0056b3',
            padding: '4px 8px',
            borderRadius: '4px',
            fontSize: '12px',
            opacity: '1',
            transition: 'opacity 0.5s',
            zIndex: '100'
        },
        innerHTML: '地址格式已自动清除',
        parent: container
    });
    
    // 设置3秒后淡出
    notification.timer = setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 500);
    }, 3000);
}

// 初始化地址清理器的事件监听
export function initializeAddressCleaner() {
    // console.log('🔄 初始化地址清理器开始...');
    
    // 页面加载时就去获取后缀列表
    fetchLocationTypeSuffixes();
    
    // 获取地址输入框元素
    const addressesTextarea = document.getElementById('addresses');
    
    if (!addressesTextarea) {
        console.error('❌ 未找到地址输入框元素 #addresses');
        return;
    }
    
    // console.log('✅ 找到地址输入框元素:', addressesTextarea);

    let isDirty = false;
    
    // 为地址输入框添加粘贴事件监听器
    addressesTextarea.addEventListener('paste', function() {
        // console.log('📋 检测到粘贴事件');
        // 使用延时，让粘贴的内容先进入文本框
        setTimeout(async () => {
            // console.log('📋 开始处理粘贴内容...');
            const oldValue = this.value;
            const newValue = cleanAddresses(this.value);
            
            // console.log('📋 粘贴清洗前:', oldValue.substring(0, 100) + (oldValue.length > 100 ? '...' : ''));
            // console.log('📋 粘贴清洗后:', newValue.substring(0, 100) + (newValue.length > 100 ? '...' : ''));
            
            if (oldValue !== newValue) {
                this.value = newValue;
                showCleanNotification(this);
                // 强制更新地址计数
                const event = new Event('input', { bubbles: true, cancelable: true });
                this.dispatchEvent(event);
                // console.log('📋 地址已清洗并更新');
            } else {
                // console.log('📋 地址无需清洗');
            }
            // 清洗后，内容是干净的
            isDirty = false; 

            // 检测并生成标签
            const addresses = newValue.split('\n').filter(line => line.trim());
            // console.log('📋 开始检测后缀，地址数量:', addresses.length);
            await detectCommonSuffix(addresses);
        }, 10);
    });
    
    // 监听内容变化，标记为"脏"
    addressesTextarea.addEventListener('input', function() {
        // console.log('✏️ 检测到输入事件，标记为脏数据');
        isDirty = true;
        // 同时，也实时进行后缀检测
        const detect = async () => {
            const addresses = this.value.split('\n').filter(line => line.trim());
            // console.log('✏️ 输入事件后缀检测，地址数量:', addresses.length);
            await detectCommonSuffix(addresses);
        };
        // 使用防抖避免过于频繁的检测
        clearTimeout(this.detectDebounceTimer);
        this.detectDebounceTimer = setTimeout(detect, 300);
    });

    // 在失焦时，如果内容变"脏"了，则进行清理
    addressesTextarea.addEventListener('blur', function() {
        // console.log('👀 检测到失焦事件，isDirty:', isDirty);
        if (isDirty) {
            const oldValue = this.value;
            const newValue = cleanAddresses(this.value);
            // console.log('👀 失焦清洗前:', oldValue.substring(0, 100) + (oldValue.length > 100 ? '...' : ''));
            // console.log('👀 失焦清洗后:', newValue.substring(0, 100) + (newValue.length > 100 ? '...' : ''));
            if (oldValue !== newValue) {
                this.value = newValue;
                // 强制更新地址计数
                const event = new Event('input', { bubbles: true, cancelable: true });
                this.dispatchEvent(event);
                // console.log('👀 失焦时地址已清洗并更新');
            } else {
                // console.log('👀 失焦时地址无需清洗');
            }
            isDirty = false;
        }
    });

    // 清理和检测函数，用于按钮点击前
    async function cleanAndDetectAddresses() {
        const addressesTextarea = document.getElementById('addresses');
        if (!addressesTextarea) return;
        
        const oldValue = addressesTextarea.value;
        const newValue = cleanAddresses(addressesTextarea.value);
        if (oldValue !== newValue) {
            addressesTextarea.value = newValue;
            showCleanNotification(addressesTextarea);
            // 强制更新地址计数
            const event = new Event('input', { bubbles: true, cancelable: true });
            addressesTextarea.dispatchEvent(event);
        }
        // 检测并生成标签
        const addresses = newValue.split('\n').filter(line => line.trim());
        await detectCommonSuffix(addresses);
    }
    
    // console.log('✅ 地址清理器初始化完成');
    
    // 导出该函数以便其他模块使用
    return { cleanAndDetectAddresses };
}