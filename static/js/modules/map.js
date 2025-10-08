import { addMarkersToMapAndFitBounds } from './utils.js';

let itemCalibrationMap; // Main map for single item view
let resultsOverviewMap; // Overview map for all selected results
let searchMarkers = []; // Markers from POI searches
let overviewMapMarkers = []; // Markers on the overview map
let singleLocationMarker = null; // Marker for showLocationOnMap

/**
 * Creates the Amap tile layers (satellite and road).
 * @returns {object} An object containing the satellite and road layers.
 */
export function createAmapTileLayers() {
    const amapSatelliteLayer = L.tileLayer('https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}', {
        subdomains: '1234',
        attribution: '© AutoNavi'
    });
    const amapRoadLayer = L.tileLayer('https://webst0{s}.is.autonavi.com/appmaptile?style=8&x={x}&y={y}&z={z}', {
        subdomains: '1234',
        attribution: '© AutoNavi'
    });
    return { satellite: amapSatelliteLayer, road: amapRoadLayer };
}

/**
 * Initializes the main item calibration map.
 * @param {string} mapId - The ID of the map container element.
 * @returns {L.Map} The initialized Leaflet map instance.
 */
export function initializeMap(mapId) {
    if (itemCalibrationMap) {
        itemCalibrationMap.remove();
    }
    const amap = createAmapTileLayers();
    const defaultBase = amap.satellite;
    itemCalibrationMap = L.map(mapId, {
        layers: [defaultBase],
        center: [35.86166, 104.195397],
        zoom: 4,
        zoomControl: false,
    });
    // 图层切换：优先展示天地图与高德两个来源
    const baseLayers = {};
    baseLayers['高德卫星'] = amap.satellite;
    baseLayers['高德街道'] = amap.road;
    L.control.layers(baseLayers, null, { position: 'topright' }).addTo(itemCalibrationMap);
    L.control.zoom({ position: 'bottomright' }).addTo(itemCalibrationMap);

    return itemCalibrationMap;
}

/**
 * Initializes the results overview map.
 * @param {string} mapId - The ID of the map container element.
 * @returns {L.Map} The initialized Leaflet map instance.
 */
export function initializeResultsOverviewMap(mapId) {
    if (resultsOverviewMap) {
        resultsOverviewMap.remove();
    }
    const amap = createAmapTileLayers();
    const defaultBase = amap.satellite;
    resultsOverviewMap = L.map(mapId, {
        layers: [defaultBase],
        center: [35.86166, 104.195397],
        zoom: 4,
        zoomControl: false,
    });
    const baseLayers = {};
    baseLayers['高德卫星'] = amap.satellite;
    baseLayers['高德街道'] = amap.road;
    L.control.layers(baseLayers, null, { position: 'topright' }).addTo(resultsOverviewMap);
    L.control.zoom({ position: 'bottomright' }).addTo(resultsOverviewMap);

    // 防护：容器在隐藏或尺寸为0时，地图会呈灰色。延迟多次重算尺寸。
    const retries = [50, 150, 400];
    retries.forEach(delay => setTimeout(() => {
        try { resultsOverviewMap.invalidateSize(); } catch (e) {}
    }, delay));

    return resultsOverviewMap;
}

/**
 * Ensures the results overview map is initialized and sized correctly.
 * Safe to call multiple times.
 * @param {string} mapId - The ID of the map container element (default 'map').
 * @returns {L.Map|null} The map instance or null if container not found.
 */
export function ensureResultsOverviewMap(mapId = 'map') {
    const container = typeof mapId === 'string' ? document.getElementById(mapId) : mapId;
    if (!container) {
        console.warn('[Map] ensureResultsOverviewMap: container not found for', mapId);
        return null;
    }
    if (resultsOverviewMap && typeof resultsOverviewMap.setView === 'function') {
        // Ensure size after becoming visible
        const rect = container.getBoundingClientRect();
        // console.log('[Map] ensureResultsOverviewMap: reuse map', { id: resultsOverviewMap._leaflet_id, w: rect.width, h: rect.height, ds: container.style.display });
        [50, 150, 400].forEach(d => setTimeout(() => { try { resultsOverviewMap.invalidateSize(); } catch (e) {} }, d));
        return resultsOverviewMap;
    }
    const map = initializeResultsOverviewMap(mapId);
    const rect = container.getBoundingClientRect();
    // console.log('[Map] ensureResultsOverviewMap: create map', { id: map._leaflet_id, w: rect.width, h: rect.height, ds: container.style.display });
    [50, 150, 400].forEach(d => setTimeout(() => { try { map.invalidateSize(); } catch (e) {} }, d));
    return map;
}

/**
 * Ensures the single item calibration map is initialized and sized correctly.
 * Safe to call multiple times.
 * @param {string} mapId - The ID of the map container element (default 'itemCalibrationMap').
 * @returns {L.Map|null} The map instance or null if container not found.
 */
export function ensureCalibrationMap(mapId = 'itemCalibrationMap') {
    const container = typeof mapId === 'string' ? document.getElementById(mapId) : mapId;
    if (!container) {
        console.warn('[Map] ensureCalibrationMap: container not found for', mapId);
        return null;
    }
    if (itemCalibrationMap && typeof itemCalibrationMap.setView === 'function') {
        const rect = container.getBoundingClientRect();
        // console.log('[Map] ensureCalibrationMap: reuse map', { id: itemCalibrationMap._leaflet_id, w: rect.width, h: rect.height, ds: container.style.display });
        [50, 150, 400].forEach(d => setTimeout(() => { try { itemCalibrationMap.invalidateSize(); } catch (e) {} }, d));
        return itemCalibrationMap;
    }
    const map = initializeMap(mapId);
    const rect = container.getBoundingClientRect();
    // console.log('[Map] ensureCalibrationMap: create map', { id: map._leaflet_id, w: rect.width, h: rect.height, ds: container.style.display });
    [50, 150, 400].forEach(d => setTimeout(() => { try { map.invalidateSize(); } catch (e) {} }, d));
    return map;
}

/**
 * Shows a specific location on the main calibration map.
 * @param {L.Map} map - The map instance.
 * @param {number} lat_gcj02 - Latitude (GCJ-02).
 * @param {number} lng_gcj02 - Longitude (GCJ-02).
 * @param {string} address - The address for the popup.
 * @param {string} details_html - Additional HTML details for the popup.
 */
export function showLocationOnMap(map, lat_gcj02, lng_gcj02, address, details_html = '') {
    if (!map) return;
    if (singleLocationMarker) {
        map.removeLayer(singleLocationMarker);
    }
    const latLng = [lat_gcj02, lng_gcj02];
    map.setView(latLng, 15);
    singleLocationMarker = L.marker(latLng).addTo(map)
        .bindPopup(`<b>${address}</b><br>${details_html}`)
        .openPopup();
}

/**
 * Clears all search markers from the main calibration map.
 * @param {L.Map} map - The map instance.
 */
export function clearSearchMarkers(map) {
    if (!map) return;
    searchMarkers.forEach(marker => map.removeLayer(marker));
    searchMarkers = [];
}

/**
 * Updates the markers on the results overview map.
 * @param {L.Map} map - The results overview map instance.
 * @param {Array} selectedResults - The array of selected result items.
 */
export function updateResultsOverviewMapMarkers(map, selectedResults) {
    if (!map || typeof map.setView !== 'function') {
        console.error('[Map] updateResultsOverviewMapMarkers: invalid map instance', map);
        return;
    }
    try {
        const container = map.getContainer && map.getContainer();
        if (container) {
            const rect = container.getBoundingClientRect();
            // console.log('[Map] container size', { width: rect.width, height: rect.height, display: container.style && container.style.display });
        }
    } catch (e) { console.warn('[Map] could not inspect map container', e); }
    // console.log('[Map] updateResultsOverviewMapMarkers: selectedResults=', Array.isArray(selectedResults) ? selectedResults.length : 'invalid');
    const getLatLngForOverviewMap = (item) => {
        if (!item.selected_result || !item.selected_result.result) return null;
        const result = item.selected_result.result;
        // 高德地图使用GCJ02坐标系，优先使用GCJ02
        const lat = result.latitude_gcj02 || result.latitude_wgs84;
        const lng = result.longitude_gcj02 || result.longitude_wgs84;
        if (lat && lng) return [parseFloat(lat), parseFloat(lng)];
        return null;
    };

    const getPopupContentForOverviewMap = (item) => {
        if (!item.selected_result || !item.selected_result.result) return '<h6>信息不完整</h6>';
        const result = item.selected_result.result;

        const title = item.address || `记录 #${item.id}`; // 使用顶层的原始地址作为标题
        const address = result.formatted_address || '无地址信息';
        const wgs84 = (result.latitude_wgs84 && result.longitude_wgs84) 
            ? `WGS84: ${result.longitude_wgs84.toFixed(6)}, ${result.latitude_wgs84.toFixed(6)}` 
            : 'WGS84: -';
        const gcj02 = (result.latitude_gcj02 && result.longitude_gcj02) 
            ? `GCJ02: ${result.longitude_gcj02.toFixed(6)}, ${result.latitude_gcj02.toFixed(6)}` 
            : 'GCJ02: -';

        return `<h6>${title}</h6><p>${address}</p><small>${wgs84}<br>${gcj02}</small>`;
    };
    
    const createIconForOverviewMap = (item, index) => {
        const icon = L.divIcon({
            className: 'numbered-marker-icon',
            html: `<span>${index + 1}</span>`,
            iconSize: [28, 28],
            iconAnchor: [14, 14],
            popupAnchor: [0, -14]
        });
        // 调试：记录图标HTML和类名
        // try { console.log('[Map] createIconForOverviewMap', { idx: index, className: icon.options && icon.options.className, html: icon.options && icon.options.html }); } catch (e) {}
        return icon;
    };

    const beforeCount = overviewMapMarkers.length;
    addMarkersToMapAndFitBounds(map, selectedResults, overviewMapMarkers, getLatLngForOverviewMap, getPopupContentForOverviewMap, createIconForOverviewMap);
    // console.log('[Map] markers before/after add:', { before: beforeCount, after: overviewMapMarkers.length });
    // 额外防护：如果地图仍未正确缩放，尝试在下一个tick再次fit。
    setTimeout(() => {
        try {
            const bounds = L.featureGroup(overviewMapMarkers).getBounds();
            if (bounds.isValid()) {
                map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
                const center = map.getCenter();
                // console.log('[Map] refit done center/zoom=', { center, zoom: map.getZoom(), markers: overviewMapMarkers.length });
                // 调试：检查第一个标记DOM可见性
                const first = overviewMapMarkers[0];
                if (first && first._icon) {
                    const style = window.getComputedStyle(first._icon);
                    // console.log('[Map] first marker icon computed style', { display: style.display, width: style.width, height: style.height, opacity: style.opacity, className: first._icon.className });
                } else {
                    // console.log('[Map] first marker icon not available yet');
                }
            } else {
                console.warn('[Map] bounds invalid');
            }
        } catch (e) {}
    }, 50);
}

/**
 * Displays all selected results on the overview map.
 * @param {L.Map} map - The results overview map instance.
 * @param {Array} selectedResults - The array of selected result items.
 */
export function showAllSelectedOnOverviewMap(map, selectedResults) {
    if (!map) return;
    document.getElementById('overviewMapModal').style.display = 'block';
    // Invalidate size to ensure map renders correctly after modal is shown
    setTimeout(() => {
        map.invalidateSize();
        updateResultsOverviewMapMarkers(map, selectedResults);
    }, 200);
}

/**
 * Highlights a specific search result on the map.
 * @param {L.Map} map - The main calibration map instance.
 * @param {number} index - The index of the marker to highlight.
 */
export function highlightMapSearchResult(map, index) {
    if (!map) return;
    if (searchMarkers[index]) {
        const marker = searchMarkers[index];
        map.setView(marker.getLatLng(), 16);
        marker.openPopup();
        
        // Add a temporary highlight class
        const iconElement = marker._icon;
        if (iconElement) {
            iconElement.classList.add('highlight-marker');
            setTimeout(() => {
                iconElement.classList.remove('highlight-marker');
            }, 2000); // Highlight for 2 seconds
        }
    }
} 