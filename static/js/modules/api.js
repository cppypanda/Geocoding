import { showLoading, hideLoading, showToast } from './utils.js';
import { ENDPOINTS } from './constants.js';
import { updateUserBar } from './auth.js';

/**
 * A wrapper for the native fetch API.
 * @param {string} url - The URL to fetch.
 * @param {object} options - Fetch options (method, headers, body, etc.).
 * @returns {Promise<object>} - A promise that resolves with the JSON response.
 */
export async function fetchAPI(url, options = {}) {
    const requestId = (window.crypto && typeof window.crypto.randomUUID === 'function')
        ? window.crypto.randomUUID()
        : `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const startedAt = Date.now();
    let phase = 'fetch';
    let responseReceived = false;
    let responseStatus = null;
    // Get CSRF token dynamically on each request to avoid cache issues
    const csrfTokenElement = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfTokenElement ? csrfTokenElement.getAttribute('content') : '';
    
    const defaultHeaders = {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest', // Mark as AJAX request
    };

    // Add Content-Type only if body is not FormData
    if (!(options.body instanceof FormData)) {
        defaultHeaders['Content-Type'] = 'application/json';
    }

    // Always add CSRF token if it exists
    if (csrfToken) {
        defaultHeaders['X-CSRFToken'] = csrfToken;
    }
    const activeTracking = window.currentGeocodingTracking || null;
    if (activeTracking?.task_id) {
        defaultHeaders['X-Geocoding-Task-ID'] = String(activeTracking.task_id);
    }
    if (activeTracking?.client_action_id) {
        defaultHeaders['X-Geocoding-Action-ID'] = String(activeTracking.client_action_id);
    }

    const config = {
        ...options,
        headers: {
            ...defaultHeaders,
            'X-Request-ID': requestId,
            ...options.headers,
        },
    };

    try {
        const response = await fetch(url, config);
        responseReceived = true;
        responseStatus = response.status;
        phase = 'response';
        
        if (response.status === 401) {
            // Unauthorized, redirect to login page or show login modal
            // This is a simple example; you might want more sophisticated handling
            showToast('请先登录', 'warning');
            // Or trigger a login modal:
            // const loginModal = new bootstrap.Modal(document.getElementById('loginModal'));
            // loginModal.show();
            throw new Error('Unauthorized'); 
        }

        if (!response.ok) {
            let errorData;
            try {
                errorData = await response.json();
            } catch (e) {
                // If the error response is not JSON, use the status text
                throw new Error(response.statusText || 'Network response was not ok');
            }
            const errorMessage = errorData.message || errorData.error || 'An unknown error occurred.';
            throw new Error(errorMessage);
        }
        
        // If the response has no content, return a success indicator
        if (response.status === 204 || response.headers.get('Content-Length') === '0') {
            return { success: true };
        }
        
        phase = 'response_json';
        return await response.json();
    } catch (error) {
        error.apiContext = {
            endpoint: String(url).split('?', 1)[0],
            requestId,
            phase,
            responseReceived,
            responseStatus,
            elapsedMs: Date.now() - startedAt,
        };
        console.error('API call failed:', error);
        showToast(`操作失败: ${error.message}`, 'danger');
        throw error;
    }
}

// Helper function to update user state
function updateUserState(user) {
    if (user && typeof user.points !== 'undefined') {
        if (window.currentUser) {
            window.currentUser.points = user.points;
        }
        updateUserBar(window.currentUser);
    }
}

// This module centralizes all API calls to the backend.

/**
 * Performs the main geocoding request.
 * @param {string[]} addresses - An array of addresses to geocode.
 * @param {string} mode - The geocoding mode ('default' or 'smart').
 * @param {string[]} locationTags - Tags for location type.
 * @returns {Promise<object>} The server's response data.
 */
export async function geocodeAddresses(addresses, mode = 'default', locationTags = [], trackingContext = {}) {
    try {
        showLoading('正在地理编码...');
        // console.log('开始地理编码请求:', { addresses, mode, locationTags });
        
        const payload = {
            addresses: addresses,
            mode: mode,
            location_tags: locationTags,
            user_id: window.currentUser ? window.currentUser.id : null,
            trigger_origin: trackingContext.trigger_origin,
            client_session_id: trackingContext.client_session_id,
            client_action_id: trackingContext.client_action_id,
        };

        const data = await fetchAPI(ENDPOINTS.geocodeProcess, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        if (data?.billing && Number.isFinite(data.billing.balance)) {
            updateUserState({ points: data.billing.balance });
        }

        // console.log('地理编码响应数据:', data);

        if (!data || !data.results) {
            console.error('地理编码响应数据无效:', data);
            throw new Error('地理编码响应数据无效');
        }

        return data;
    } catch (error) {
        console.error('地理编码过程出错:', error);
        // The error is already a proper Error object from fetchAPI
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
        return await fetchAPI('/save_location_type', {
            method: 'POST',
            body: JSON.stringify({ type: type })
        });
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
        // Get CSRF token dynamically
        const csrfTokenElement = document.querySelector('meta[name="csrf-token"]');
        const csrfToken = csrfTokenElement ? csrfTokenElement.getAttribute('content') : '';
        
        const response = await fetch(ENDPOINTS.export, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
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
        const blob = await response.blob();
        const updatedPoints = response.headers.get('X-Updated-User-Points');
        
        return {
            blob: blob,
            points: updatedPoints !== null ? parseInt(updatedPoints, 10) : null
        };
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
export async function performMapSearch(searchTerm, source = 'baidu') {
    // console.log(`开始地图搜索 (源: ${source}): ${searchTerm}`);
    const endpoint = ENDPOINTS.geocodePoiSearch;
    try {
        const data = await fetchAPI(endpoint, {
            method: 'POST',
            body: JSON.stringify({
                keyword: searchTerm, // The backend expects 'keyword'
                source: source // Pass the source ('amap', 'baidu', etc.) to the backend
            })
        });

        // console.log(`地图搜索响应数据 (${source}):`, data);
        if (data.user) {
            updateUserState(data.user);
        }
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
export async function autoSelectPoint(poiResults, originalAddress, sourceContext) {
    try {
        // console.log('[DEBUG] Calling autoSelectPoint API with:', { poiResults, originalAddress, sourceContext });
        const response = await fetchAPI(ENDPOINTS.geocodeAutoSelect, {
            method: 'POST',
            body: JSON.stringify({
                poi_results: poiResults,
                original_address: originalAddress,
                source_context: sourceContext
            })
        });
        // console.log('[DEBUG] autoSelectPoint raw API response:', response);

        if (!response.success) {
            // Rethrow the error object to be caught by the calling function's catch block
            const error = new Error(response.message || 'Auto select failed');
            error.response = response; // Attach full response for more context
            throw error;
        }
        return response;
    } catch (error) {
        const context = error.apiContext || {};
        if (!context.responseReceived) {
            window.reportClientError?.({
                kind: 'network',
                type: error.name || 'FetchNetworkError',
                message: '智能选择请求在浏览器连接层失败',
                stack: error.stack || '',
                location: ENDPOINTS.geocodeAutoSelect,
                context: {
                    operation: 'auto_select_point',
                    request_id: context.requestId || null,
                    phase: context.phase || 'unknown',
                    elapsed_ms: context.elapsedMs ?? null,
                    response_received: false,
                    browser_online: navigator.onLine,
                    page_visibility: document.visibilityState,
                    candidate_count: Array.isArray(poiResults) ? poiResults.length : 0,
                    source_context: String(sourceContext || '').slice(0, 80),
                }
            });
        }
        // console.error('[DEBUG] Error in autoSelectPoint API call:', error);
        // Re-throw the error so the calling function knows the operation failed.
        // This is crucial for the UI to react correctly (e.g., stop loading spinners).
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
        const data = await fetchAPI('/smart_search', {
            method: 'POST',
            body: JSON.stringify({ query, mode })
        });
        if (data.user) {
            updateUserState(data.user);
        }
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
        const data = await fetchAPI(ENDPOINTS.geocodeReverse, {
            method: 'POST',
            body: JSON.stringify({
                lat: lat,
                lng: lng,
                source: source
            })
        });

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
        
        const data = await fetchAPI(ENDPOINTS.geocodeConfidenceSelect, {
            method: 'POST',
            body: JSON.stringify({
                original_address: originalAddress,
                pois: pois,
                source_context: sourceContext
            })
        });
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
        
        const data = await fetchAPI(ENDPOINTS.geocodeHybridSelect, {
            method: 'POST',
            body: JSON.stringify({
                original_address: originalAddress,
                source_context: sourceContext
            })
        });

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
