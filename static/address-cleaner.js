/**
 * 地址清理工具
 * 用于清理地址列表，去除序号、缩进、空格和空行
 */

// 清理地址列表函数
function cleanAddresses(text) {
    if (!text) return '';

    // 按行分割
    let lines = text.split('\n');
    
    // 处理每一行
    let cleanedLines = lines.map(line => {
        // 去除前后空白
        line = line.trim();
        
        // 跳过空行
        if (!line) return '';
        
        // 移除序号（如"1."、"1、"、"1）"、"（1）"、"1．"等格式）
        line = line.replace(/^\s*(\d+\.|\d+、|\d+\)|\（\d+\）|\(\d+\)|\d+．)\s*/, '');
        
        // 去除全角空格和其他空白字符
        line = line.replace(/\s+/g, '');
        
        // 如果只剩下数字或为空，直接返回空字符串
        if (/^\d*$/.test(line)) return '';
        
        // 如果只剩下括号数字（如（1）或(1)），也清除
        if (/^\(?\d+\)?$/.test(line) || /^（\d+）$/.test(line)) return '';
        
        return line;
    });
    
    // 过滤掉空行
    cleanedLines = cleanedLines.filter(line => line.length > 0);
    
    return cleanedLines.join('\n');
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
async function detectCommonSuffix(addresses) {
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
        if (typeof addLocationTypeTag === 'function') {
            addLocationTypeTag(suffix);
        }
    });
}

// 保存新的地名类型后缀到数据库
async function saveLocationTypeSuffix(suffix) {
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
    const notification = document.createElement('div');
    notification.id = 'clean-notification';
    notification.style.cssText = `
        position: absolute;
        bottom: 5px;
        right: 10px;
        background-color: rgba(0, 123, 255, 0.1);
        color: #0056b3;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        opacity: 1;
        transition: opacity 0.5s;
        z-index: 100;
    `;
    notification.innerText = '地址格式已自动清除';
    
    // 将提示添加到文本框的父容器中
    const container = textarea.parentNode;
    container.style.position = 'relative';
    container.appendChild(notification);
    
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

// 在文档加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 加载后缀列表
    fetchLocationTypeSuffixes();
    
    // 获取地址输入框元素
    const addressesTextarea = document.getElementById('addresses');
    
    if (!addressesTextarea) return;
    
    // 为地址输入框添加粘贴事件监听器
    addressesTextarea.addEventListener('paste', function() {
        // 使用延时，让粘贴的内容先进入文本框
        setTimeout(async () => {
            const oldValue = this.value;
            const newValue = cleanAddresses(this.value);
            
            if (oldValue !== newValue) {
                this.value = newValue;
                showCleanNotification(this);
            }
            // 检测并生成标签（不再填入输入框）
            const addresses = newValue.split('\n').filter(line => line.trim());
            await detectCommonSuffix(addresses);
        }, 10);
    });
    
    // 为地址输入框添加输入事件监听器
    addressesTextarea.addEventListener('input', async function() {
        // 检测并生成标签（不再填入输入框）
        const addresses = this.value.split('\n').filter(line => line.trim());
        await detectCommonSuffix(addresses);
    });
    
    // 地理编码按钮的事件绑定已在其他地方处理
    
    // 地理编码按钮的事件绑定已在其他地方处理，这里只处理地址清理功能
    async function cleanAndDetectAddresses() {
        const oldValue = addressesTextarea.value;
        const newValue = cleanAddresses(addressesTextarea.value);
        if (oldValue !== newValue) {
            addressesTextarea.value = newValue;
            showCleanNotification(addressesTextarea);
        }
        // 检测并生成标签（不再填入输入框）
        const addresses = newValue.split('\n').filter(line => line.trim());
        await detectCommonSuffix(addresses);
    }

    // 在原有的事件处理程序之前添加地址清理功能
    document.addEventListener('click', async function(e) {
        if (e.target.id === 'smartGeocodeBtn' || e.target.id === 'normalGeocodeBtn') {
            await cleanAndDetectAddresses();
        }
    });
}); 