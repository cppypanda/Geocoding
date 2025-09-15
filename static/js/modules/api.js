import { showLoading, hideLoading, showToast } from './utils.js';
import { ENDPOINTS } from './constants.js';

// This module centralizes all API calls to the backend.

/**
 * Performs the main geocoding request.
 * @param {string[]} addresses - An array of addresses to geocode.
 * @param {string} mode - The geocoding mode ('default' or 'smart').
 * @param {string[]} locationTags - Tags for location type.
 * @returns {Promise<object>} The server's response data.
 */
export async function geocodeAddresses(addresses, mode = 'default', locationTags = []) {
    try {
        showLoading('正在地理编码...');
        // console.log('开始地理编码请求:', { addresses, mode, locationTags });
        
        const payload = {
            addresses: addresses,
            mode: mode,
            location_tags: locationTags,
            user_id: window.currentUser ? window.currentUser.id : null
        };

        const response = await fetch(ENDPOINTS.geocodeProcess, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('地理编码请求失败:', {
                status: response.status,
                statusText: response.statusText,
                error: errorText
            });
            throw new Error(`地理编码请求失败: ${response.status} ${response.statusText}`);
        }

        const data = await response.json();
        // console.log('地理编码响应数据:', data);

        if (!data || !data.results) {
            console.error('地理编码响应数据无效:', data);
            throw new Error('地理编码响应数据无效');
        }

        return data;
    } catch (error) {
        console.error('地理编码过程出错:', error);
        throw error;
    } finally {
        hideLoading();
    }
}

/**
 * Performs a "smart search" for multiple addresses in batch.
 * @param {Array<object>} results - Array of result objects, each must have an 'address' property.
 * @returns {Promise<Array<object>>} A promise that resolves to an array of results from the API calls.
 */
export async function smartSelectAll(results) {
    if (!results || results.length === 0) {
        return Promise.resolve([]);
    }

    // Create a promise for each address. Note that we are calling the single match function.
    const promises = results.map(result => {
        // Ensure result and result.address exist to avoid errors
        if (result && result.address) {
            return performSingleIntelligentMatch({ address: result.address });
        }
        return Promise.resolve(null); // Return a resolved promise for invalid items
    });

    // Use Promise.allSettled to ensure all requests are processed even if some fail
    const outcomes = await Promise.allSettled(promises);

    const successfulResults = [];
    const failedReasons = [];

    outcomes.forEach(outcome => {
        if (outcome.status === 'fulfilled' && outcome.value) {
            successfulResults.push(outcome.value);
        } else if (outcome.status === 'rejected') {
            failedReasons.push(outcome.reason);
        }
    });

    if (failedReasons.length > 0) {
        console.error('部分智能匹配失败:', failedReasons);
        // We can still return successful results and let the caller decide how to handle failures.
    }
    
    return successfulResults;
}

/**
 * Saves a new location type tag to the server.
 * @param {string} type - The location type tag to save.
 * @returns {Promise<object>} The server's response data.
 */
export async function saveLocationTypeToServer(type) {
    if (!type) return;
    try {
        const response = await fetch('/save_location_type', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type: type })
        });
        return await response.json();
    } catch (error) {
        console.error('保存地名类型后缀失败:', error);
        throw error;
    }
}

/**
 * Requests file export from the server.
 * @param {string} format - The desired file format (e.g., 'xlsx', 'kml').
 * @param {Array} data - The data to be exported.
 * @param {string} locationName - The name for the export file.
 * @returns {Promise<Blob>} A promise that resolves with the file blob.
 */
export async function exportData(format, data, locationName) {
    try {
        const response = await fetch(ENDPOINTS.export, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                format: format,
                data: data,
                location_name: locationName
            })
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ error: '服务器返回了无效的错误信息' }));
            throw new Error(errorData.error || `导出 ${format.toUpperCase()} 文件失败`);
        }
        return await response.blob();
    } catch (error) {
        console.error('导出失败:', error);
        throw error; // Re-throw to be caught by the calling function
    }
}

/**
 * Performs a map search using a given source.
 * @param {string} searchTerm - The search term.
 * @param {string} source - The search source ('amap', 'baidu', 'tianditu').
 * @returns {Promise<Object>} The search results from the API.
 */
export async function performMapSearch(searchTerm, source = 'amap') {
    // console.log(`开始地图搜索 (源: ${source}): ${searchTerm}`);
    const endpoint = ENDPOINTS.geocodePoiSearch;
    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                keyword: searchTerm, // The backend expects 'keyword'
                source: source // Pass the source ('amap', 'baidu', etc.) to the backend
            })
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.message || `HTTP error! status: ${response.status}`);
        }
        // console.log(`地图搜索响应数据 (${source}):`, data);
        return data;
    } catch (error) {
        console.error(`地图搜索错误 (${source}):`, error);
        throw error; // Re-throw the error to be caught by the caller
    }
}

/**
 * Uses LLM to intelligently select the best POI from a list based on an address.
 * @param {Array} pois - The list of POI candidates from a map search.
 * @param {string} originalAddress - The original address for context.
 * @param {string} sourceContext - The source context for the search.
 * @returns {Promise<object>} The server's response with the selected point index.
 */
export async function autoSelectPoint(pois, originalAddress, sourceContext) {
    try {
        const response = await fetch(ENDPOINTS.geocodeAutoSelect, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                original_address: originalAddress,
                pois: pois,
                source_context: sourceContext
            })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.message || '自动选点请求失败');
        return data;
    } catch (error) {
        console.error('自动选点失败:', error);
        throw error;
    }
}



/**
 * Performs a smart search (address analysis).
 * @param {string} query - The search query.
 * @param {string} mode - The search mode ('crawl_extract' or 'web_llm').
 * @returns {Promise<object>} The server's response data.
 */
export async function performSmartSearch(query, mode = 'crawl_extract') {
    showLoading('智能分析中...');
    try {
        const response = await fetch('/smart_search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, mode })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '智能分析请求失败');
        return data;
    } catch(error) {
        showToast('智能分析失败: ' + error.message, 'error');
        throw error;
    } finally {
        hideLoading();
    }
}

/**
 * Performs reverse geocoding for a given lat/lng.
 * @param {number} lat - Latitude.
 * @param {number} lng - Longitude.
 * @param {string} source - The coordinate source ('amap', 'baidu', 'tianditu').
 * @returns {Promise<object>} A promise that resolves to the reverse geocoded address data.
 */
export async function reverseGeocode(lat, lng, source = 'amap') {
    try {
        const response = await fetch(ENDPOINTS.geocodeReverse, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                lat: lat,
                lng: lng,
                source: source
            })
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.message || `HTTP error! status: ${response.status}`);
        }

        if (data.success) {
            return {
                success: true,
                formatted_address: data.formatted_address,
                address_components: data.address_components
            };
        } else {
            return { success: false, error: data.message || '逆地理编码失败' };
        }
    } catch (error) {
        console.error('反向地理编码失败:', error);
        return { success: false, error: error.message };
    }
}

/**
 * 执行置信度选点
 * @param {string} originalAddress - 原始地址
 * @param {Array} pois - POI列表
 * @param {string} sourceContext - 来源上下文
 * @returns {Promise<object>} 选点结果
 */
export async function confidenceSelectPoint(originalAddress, pois, sourceContext = '置信度选点') {
    try {
        // console.log('开始置信度选点:', { originalAddress, poisCount: pois.length, sourceContext });
        
        const response = await fetch(ENDPOINTS.geocodeConfidenceSelect, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                original_address: originalAddress,
                pois: pois,
                source_context: sourceContext
            })
        });

        const data = await response.json();
        // console.log('置信度选点响应:', data);
        
        return data;
    } catch (error) {
        console.error('置信度选点失败:', error);
        return { success: false, message: error.message };
    }
}

/**
 * 执行混合选点 (智能搜索的核心功能)
 * @param {string} originalAddress - 原始地址
 * @param {string} sourceContext - 来源上下文
 * @returns {Promise<object>} 选点结果
 */
export async function hybridSelectPoint(originalAddress, sourceContext = '智能搜索') {
    showLoading('🔍 智能分析中...');
    try {
        // console.log('开始混合选点:', { originalAddress, sourceContext });
        
        const response = await fetch(ENDPOINTS.geocodeHybridSelect, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                original_address: originalAddress,
                source_context: sourceContext
            })
        });

        const data = await response.json();
        // console.log('混合选点响应:', data);
        
        return data;
    } catch (error) {
        console.error('混合选点失败:', error);
        return { success: false, message: error.message };
    } finally {
        hideLoading();
    }
}

/**
 * 执行POI智能搜索 (完整的混合选点流程)
 * @param {string} originalAddress - 原始地址
 * @param {string} sourceContext - 来源上下文
 * @returns {Promise<object>} 搜索和选点结果
 */
export async function performPoiSmartSearch(originalAddress, sourceContext = '智能搜索') {
    return await hybridSelectPoint(originalAddress, sourceContext);
}