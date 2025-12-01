// 统一归一API标识，去掉如 "_re-geocoded"、"_reverse" 等后缀
export function normalizeApiKey(api) {
    if (!api) return 'unknown';
    const str = String(api).toLowerCase();
    // 保留 *_poi 原样用于POI显示
    if (str.endsWith('_poi')) return str;
    if (str.includes('amap')) return 'amap';
    if (str.includes('baidu')) return 'baidu';
    if (str.includes('tianditu')) return 'tianditu';
    if (str.includes('manual')) return 'manual_mark';
    return str;
}

export function getApiName(api) {
    const base = normalizeApiKey(api);
    const names = {
        amap: '高德',
        tianditu: '天地图',
        baidu: '百度',
        manual_mark: '手动选点',
        amap_poi: '高德POI',
        baidu_poi: '百度POI',
        tianditu_poi: '天地图POI'
    };
    return names[base] || api;
}

export function getApiBadgeColor(api) {
    const base = normalizeApiKey(api);
    const colors = {
        amap: 'primary',
        tianditu: 'warning', // 橙色
        baidu: 'danger',  // 红色
        manual_mark: 'info', // 青色
        selected: 'dark',
        amap_poi: 'primary',
        tianditu_poi: 'warning',
        baidu_poi: 'danger'
    };
    return `bg-${colors[base] || 'secondary'}`;
}

export function getApiMarkerHtml(api) {
    const apiStyles = {
        'amap':    { char: '高', color: '#0d6efd' }, // Bootstrap Primary Blue
        'baidu':   { char: '百', color: '#dc3545' }, // Bootstrap Danger Red
        'tianditu':{ char: '天', color: '#ffc107' }  // Bootstrap Warning Orange
    };
    const style = apiStyles[api];
    if (style) {
        return `<div class="custom-map-marker" style="background-color: ${style.color};">${style.char}</div>`;
    }
    return `<div class="custom-map-marker" style="background-color: #6c757d;">?</div>`; // Default grey
}

export function getMarkerIcon(confidence) {
    // 使用内联SVG动态生成带颜色的图钉图标，以取代不可靠的外部图片链接
    const isHighConfidence = confidence >= 0.9;
    const pinColor = isHighConfidence ? 'green' : 'red';
    
    // 这是一个标准的地图图钉SVG路径
    const svgPath = "M12 0C7.802 0 4 3.802 4 8.5c0 4.885 6.265 14.339 7.432 15.358a1 1 0 001.136 0C13.735 22.839 20 13.385 20 8.5 20 3.802 16.198 0 12 0zm0 12a3 3 0 110-6 3 3 0 010 6z";

    const iconHtml = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="25" height="41">
            <path fill="${pinColor}" stroke="white" stroke-width="0.5" d="${svgPath}"></path>
        </svg>`;

    return L.divIcon({
        html: iconHtml,
        className: 'custom-svg-icon', // Use a class to remove default leaflet icon styles
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34]
    });
}

// --- Location type suffix utilities ---
let cachedLocationTypeSuffixes = [];

// Default fallback suffixes when server list is unavailable
const DEFAULT_LOCATION_SUFFIXES = [
    '历史文化街区', '农业科技园区', '经济技术开发区', '高新技术产业开发区',
    '产业园区', '国家公园', '风景名胜区', '自然保护区', '示范区',
    '工业园区', '文化街区', '开发区', '商业区', '科技园', '公园',
    '校区', '景区', '园区', '街区'
];

export async function loadLocationTypeSuffixes() {
    if (cachedLocationTypeSuffixes.length > 0) return cachedLocationTypeSuffixes;
    try {
        const res = await fetch('/get_location_types');
        const data = await res.json();
        if (data && data.success && Array.isArray(data.types)) {
            cachedLocationTypeSuffixes = data.types.sort((a, b) => b.length - a.length);
        }
    } catch (e) {
        // Ignore fetch errors; fall back to defaults
    }
    if (cachedLocationTypeSuffixes.length === 0) {
        cachedLocationTypeSuffixes = [...DEFAULT_LOCATION_SUFFIXES];
    }
    return cachedLocationTypeSuffixes;
}

export function stripLocationTypeSuffix(address) {
    if (!address || typeof address !== 'string') return address;
    const suffixes = cachedLocationTypeSuffixes.length > 0 ? cachedLocationTypeSuffixes : DEFAULT_LOCATION_SUFFIXES;
    // Ensure longest suffixes checked first
    const sorted = [...suffixes].sort((a, b) => b.length - a.length);
    for (const s of sorted) {
        if (s && address.endsWith(s)) {
            return address.slice(0, -s.length);
        }
    }
    return address;
}

export function formatConfidence(confidence) {
    if (!confidence && confidence !== 0) return '-';
    const value = (confidence * 100).toFixed(1);
    const color = value >= 90 ? 'success' : (value >= 70 ? 'warning' : 'danger');
    return `<span class="badge bg-${color}">${value}%</span>`;
}

export function logToConsole(message, level = 'info') {
    if (typeof console === 'object') {
        if (level === 'info') {
            // console.log(message);
        } else if (level === 'warn') {
            console.warn(message);
        } else if (level === 'error') {
            console.error(message);
        }
    }
}

export function formatCoordinatesHtml(result) {
    let wgs84Text = 'WGS84: 未提供';
    if (typeof result.latitude_wgs84 === 'number' && !isNaN(result.latitude_wgs84) &&
        typeof result.longitude_wgs84 === 'number' && !isNaN(result.longitude_wgs84)) {
        wgs84Text = `WGS84: ${result.longitude_wgs84.toFixed(6)}, ${result.latitude_wgs84.toFixed(6)}`;
    }

    let gcj02Text = 'GCJ02: 未提供';
    if (typeof result.latitude_gcj02 === 'number' && !isNaN(result.latitude_gcj02) &&
        typeof result.longitude_gcj02 === 'number' && !isNaN(result.longitude_gcj02)) {
        gcj02Text = `GCJ02: ${result.longitude_gcj02.toFixed(6)}, ${result.latitude_gcj02.toFixed(6)}`;
    }
    return `<p><small>${wgs84Text}</small></p><p><small>${gcj02Text}</small></p>`;
}

export function createAndAppendElement(tagName, attributes = {}, parent = null) {
    const el = document.createElement(tagName);
    for (const key in attributes) {
        if (key === 'textContent') {
            el.textContent = attributes[key];
        } else if (key === 'innerHTML') {
            el.innerHTML = attributes[key];
        } else if (key === 'className') {
            el.className = attributes[key];
        } else if (key === 'styles' && attributes.styles && typeof attributes.styles === 'object') {
            Object.assign(el.style, attributes.styles);
        } else if (key === 'parent') {
            parent = attributes.parent;
        } else {
            el.setAttribute(key, attributes[key]);
        }
    }
    if (parent) {
        parent.appendChild(el);
    }
    return el;
}

export function showLoading(message = '加载中...') {
    let overlay = document.getElementById('loadingOverlay');
    if (!overlay) {
        overlay = createAndAppendElement('div', {
            id: 'loadingOverlay',
            styles: {
                position: 'fixed',
                top: '0',
                left: '0',
                width: '100%',
                height: '100%',
                backgroundColor: 'rgba(0,0,0,0.5)',
                zIndex: '9998'
            },
            parent: document.body
        });
    }
    overlay.style.display = 'block';

    let loading = document.getElementById('loadingSpinner');
    if (!loading) {
        loading = createAndAppendElement('div', {
            id: 'loadingSpinner',
            className: 'position-fixed top-50 start-50 translate-middle',
            styles: { zIndex: '9999' },
            innerHTML: `<div class="spinner-border text-primary" role="status"><span class="visually-hidden">${message}</span></div><div class="mt-2 text-primary">${message}</div>`,
            parent: document.body
        });
    } else {
         const spinnerText = loading.querySelector('.visually-hidden');
         const loadingMessageDiv = loading.querySelector('.text-primary');
         if (spinnerText) spinnerText.textContent = message;
         if (loadingMessageDiv && loadingMessageDiv.matches('.mt-2.text-primary')) loadingMessageDiv.textContent = message;
    }
    loading.style.display = 'block';
    document.body.style.overflow = 'hidden';
}

export function hideLoading() {
    const loading = document.getElementById('loadingSpinner');
    const overlay = document.getElementById('loadingOverlay');
    if (loading) loading.style.display = 'none';
    if (overlay) overlay.style.display = 'none';
    document.body.style.overflow = '';
}

export function showToast(message, type = 'info') {
    const toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        console.error('Toast container not found. Make sure it exists in index.html.');
        return;
    }

    const toastId = `toast-${new Date().getTime()}`;
    
    // Define colors and icons based on type
    const toastConfigs = {
        'success': { bgClass: 'bg-success', icon: '✅', title: '成功' },
        'error': { bgClass: 'bg-danger', icon: '❌', title: '错误' },
        'warning': { bgClass: 'bg-warning', icon: '⚠️', title: '警告' },
        'info': { bgClass: 'bg-info', icon: 'ℹ️', title: '通知' }
    };
    
    const config = toastConfigs[type] || toastConfigs['info'];

    const toastHTML = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
          <div class="toast-header ${config.bgClass} text-white">
            <span class="me-2">${config.icon}</span>
            <strong class="me-auto">${config.title}</strong>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
          </div>
          <div class="toast-body">
            ${message}
          </div>
        </div>`;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHTML);
    
    const toastElement = document.getElementById(toastId);
    
    if (toastElement) {
        const toast = new bootstrap.Toast(toastElement);
        toast.show();
        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    }
}

export function buildTableRows(tbody, dataItems, rowHtmlGenerator) {
    if (!tbody) {
        console.error('Table body element is not provided.');
        return;
    }
    tbody.innerHTML = ''; 

    if (!dataItems || dataItems.length === 0) {
        return;
    }

    dataItems.forEach((item, index) => {
        const row = tbody.insertRow();
        row.innerHTML = rowHtmlGenerator(item, index); 
    });
}

/**
 * 在地图上添加标记并自动缩放以适应边界。
 * 该函数经过重载以兼容新旧两种调用方式。
 * 
 * 旧用法 (用于校准面板): addMarkersToMapAndFitBounds(map, pointsArray)
 * - map: Leaflet地图实例。
 * - pointsArray: 坐标数组，例如 [[lat1, lng1], [lat2, lng2]]。
 * 
 * 新用法 (用于主结果列表): addMarkersToMapAndFitBounds(mapInstance, dataItems, markerArray, getLatLngFunction, ...)
 */
export function addMarkersToMapAndFitBounds(mapInstance, dataOrPoints, markerArray, getLatLngFunction, getPopupContentFunction, createIconFunction) {
    if (!mapInstance) {
        console.error('Map instance is not provided.');
        return;
    }
    try {
        /* console.log('[utils] addMarkersToMapAndFitBounds', {
            hasMarkerArray: Array.isArray(markerArray),
            dataType: Array.isArray(dataOrPoints) ? 'array' : typeof dataOrPoints,
            dataLength: Array.isArray(dataOrPoints) ? dataOrPoints.length : undefined
        }); */
    } catch (e) {}
    
    // 清除现有标记 (适用于两种情况)
    // 如果 markerArray 提供了，就用它来清除，否则清除地图上所有 marker
    if (Array.isArray(markerArray)) {
        markerArray.forEach(marker => mapInstance.removeLayer(marker));
        markerArray.length = 0;
    } else {
        mapInstance.eachLayer(layer => {
            if (layer instanceof L.Marker || layer instanceof L.CircleMarker) {
                mapInstance.removeLayer(layer);
            }
        });
    }

    // 判断是新用法还是旧用法
    const isOldUsage = Array.isArray(dataOrPoints) && dataOrPoints.every(p => Array.isArray(p) && typeof p[0] === 'number');

    let validPointsForBounds = [];
    let markersToAdd = [];

    if (isOldUsage) {
        // --- 旧用法逻辑 ---
        validPointsForBounds = dataOrPoints;
        dataOrPoints.forEach(point => {
            const marker = L.marker(point);
            markersToAdd.push(marker);
        });

    } else {
        // --- 新用法逻辑 ---
        const dataItems = dataOrPoints;
        if (!Array.isArray(dataItems) || !getLatLngFunction) {
            mapInstance.setView([35.86166, 104.195397], 4);
            return;
        }

        dataItems.forEach((item, index) => {
            const latLng = getLatLngFunction(item);
            if (latLng && typeof latLng[0] === 'number' && typeof latLng[1] === 'number') {
                const popupContent = getPopupContentFunction ? getPopupContentFunction(item) : '';
                const icon = createIconFunction ? createIconFunction(item, index) : undefined;
                // console.log('[utils] creating marker', { index, latLng, hasIcon: !!icon, iconClass: icon && icon.options && icon.options.className });
                const marker = L.marker(latLng, { icon: icon }).bindPopup(popupContent);
                markersToAdd.push(marker);
                if (Array.isArray(markerArray)) markerArray.push(marker);
                validPointsForBounds.push(latLng);
            } else {
                console.warn('[utils] invalid latLng for item index', index, 'item=', item);
            }
        });
    }

    // 将所有准备好的标记添加到地图上并调整视图
    if (markersToAdd.length > 0) {
        const markerGroup = L.featureGroup(markersToAdd).addTo(mapInstance);
        if (validPointsForBounds.length > 0) {
            mapInstance.fitBounds(markerGroup.getBounds(), { padding: [40, 40], maxZoom: 16 });
        }
    } else {
        mapInstance.setView([35.86166, 104.195397], 4); // 如果没有点，则重置视图
    }
    
    // console.log('[utils] map updated with markers', { count: markersToAdd.length });
}

// 新策略：前端不再声明或使用积分消耗常量

// 坐标转换函数
function outOfChina(lng, lat) {
    return !(lng > 73.66 && lng < 135.05 && lat > 3.86 && lat < 53.55);
}

function transformLat(lng, lat) {
    const PI = 3.1415926535897932384626;
    let ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 
              0.1 * lng * lat + 0.2 * Math.sqrt(Math.abs(lng));
    ret += (20.0 * Math.sin(6.0 * lng * PI) + 20.0 * 
            Math.sin(2.0 * lng * PI)) * 2.0 / 3.0;
    ret += (20.0 * Math.sin(lat * PI) + 40.0 * 
            Math.sin(lat / 3.0 * PI)) * 2.0 / 3.0;
    ret += (160.0 * Math.sin(lat / 12.0 * PI) + 320 * 
            Math.sin(lat * PI / 30.0)) * 2.0 / 3.0;
    return ret;
}

function transformLng(lng, lat) {
    const PI = 3.1415926535897932384626;
    let ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 
              0.1 * lng * lat + 0.1 * Math.sqrt(Math.abs(lng));
    ret += (20.0 * Math.sin(6.0 * lng * PI) + 20.0 * 
            Math.sin(2.0 * lng * PI)) * 2.0 / 3.0;
    ret += (20.0 * Math.sin(lng * PI) + 40.0 * 
            Math.sin(lng / 3.0 * PI)) * 2.0 / 3.0;
    ret += (150.0 * Math.sin(lng / 12.0 * PI) + 300.0 * 
            Math.sin(lng / 30.0 * PI)) * 2.0 / 3.0;
    return ret;
}

/**
 * GCJ02(火星坐标系)转WGS84
 */
export function gcj02ToWgs84(lng, lat) {
    if (outOfChina(lng, lat)) {
        return { longitude: lng, latitude: lat };
    }
    
    const PI = 3.1415926535897932384626;
    const ee = 0.00669342162296594323;
    const a = 6378245.0;
    
    let dlat = transformLat(lng - 105.0, lat - 35.0);
    let dlng = transformLng(lng - 105.0, lat - 35.0);
    const radlat = lat / 180.0 * PI;
    let magic = Math.sin(radlat);
    magic = 1 - ee * magic * magic;
    const sqrtmagic = Math.sqrt(magic);
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * PI);
    dlng = (dlng * 180.0) / (a / sqrtmagic * Math.cos(radlat) * PI);
    const mglat = lat + dlat;
    const mglng = lng + dlng;
    
    return {
        longitude: lng * 2 - mglng,
        latitude: lat * 2 - mglat
    };
}

/**
 * WGS84转GCJ02(火星坐标系)
 */
export function wgs84ToGcj02(lng, lat) {
    if (outOfChina(lng, lat)) {
        return { longitude: lng, latitude: lat };
    }
    
    const PI = 3.1415926535897932384626;
    const ee = 0.00669342162296594323;
    const a = 6378245.0;
    
    let dlat = transformLat(lng - 105.0, lat - 35.0);
    let dlng = transformLng(lng - 105.0, lat - 35.0);
    const radlat = lat / 180.0 * PI;
    let magic = Math.sin(radlat);
    magic = 1 - ee * magic * magic;
    const sqrtmagic = Math.sqrt(magic);
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * PI);
    dlng = (dlng * 180.0) / (a / sqrtmagic * Math.cos(radlat) * PI);
    const mglat = lat + dlat;
    const mglng = lng + dlng;
    
    return {
        longitude: mglng,
        latitude: mglat
    };
}

/**
 * 通用坐标转换函数
 */
export function convertCoordinates(lng, lat, fromSystem, toSystem) {
    if (fromSystem === 'GCJ02' && toSystem === 'WGS84') {
        return gcj02ToWgs84(lng, lat);
    } else if (fromSystem === 'WGS84' && toSystem === 'GCJ02') {
        return wgs84ToGcj02(lng, lat);
    } else {
        throw new Error(`不支持的坐标转换: ${fromSystem} -> ${toSystem}`);
    }
}

/**
 * 显示“积分已耗光”模态框
 */
export function showPointsExhaustedModal() {
    let modalEl = document.getElementById('pointsExhaustedModal');
    // 如果模态框不存在，则动态创建
    if (!modalEl) {
        const modalHTML = `
        <div class="modal fade" id="pointsExhaustedModal" tabindex="-1" aria-hidden="true">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content" style="border-radius: 25px;">
                    <div class="modal-header border-0">
                        <h5 class="modal-title fw-bold"><i class="bi bi-exclamation-circle text-warning me-2"></i>积分不足</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body text-center py-4">
                        <p class="mb-4 lead" style="font-size: 1.1rem;">您的积分已耗光，无法继续进行此操作。<br><span class="text-muted small">请获取免费积分或充值以继续使用。</span></p>
                        <div class="d-grid gap-3 col-10 mx-auto">
                             <button type="button" class="btn btn-outline-info" id="exhaustedFreePointsBtn"><i class="bi bi-gift"></i> 免费赚积分</button>
                            <button type="button" class="btn btn-primary" id="exhaustedRechargeBtn"><i class="bi bi-credit-card"></i> 积分充值</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        modalEl = document.getElementById('pointsExhaustedModal');
        
        // 绑定按钮事件
        const freeBtn = document.getElementById('exhaustedFreePointsBtn');
        const rechargeBtn = document.getElementById('exhaustedRechargeBtn');
        
        if (freeBtn) {
            freeBtn.addEventListener('click', () => {
                const m = bootstrap.Modal.getInstance(modalEl);
                if (m) m.hide();
                const freeModalEl = document.getElementById('freePointsModal');
                if (freeModalEl) {
                    const freeModal = bootstrap.Modal.getOrCreateInstance(freeModalEl);
                    freeModal.show();
                }
            });
        }
        
        if (rechargeBtn) {
            rechargeBtn.addEventListener('click', () => {
                const m = bootstrap.Modal.getInstance(modalEl);
                if (m) m.hide();
                const rechargeModalEl = document.getElementById('rechargeModal');
                if (rechargeModalEl) {
                    const rechargeModal = bootstrap.Modal.getOrCreateInstance(rechargeModalEl);
                    rechargeModal.show();
                }
            });
        }
    }
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
}

/**
 * 检查用户积分是否足够（> 0）。
 * 如果积分为0或更少，显示警告模态框并返回 false。
 * 如果用户未登录（currentUser 为 null），则返回 true (让后续流程处理登录检查) 或 false (取决于策略)。
 * 此处假设登录检查由其他逻辑处理，仅关注已登录且积分为0的情况。
 */
export function checkUserPoints() {
    const user = window.currentUser;
    // 如果未登录，暂时放行，由登录检查逻辑拦截（通常这些按钮操作前都会查登录）
    if (!user) {
        return true; 
    }
    
    // 如果已登录且积分为 0 (或负数)
    if (user.points !== undefined && user.points <= 0) {
        showPointsExhaustedModal();
        return false;
    }
    return true;
}
