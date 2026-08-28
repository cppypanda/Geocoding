import { fetchAPI } from './api.js';

const SESSION_KEY = 'geoco.analytics.session_id';
const exposedButtons = new Set();

function newClientId(prefix = 'evt') {
    let value;
    try {
        value = crypto.randomUUID();
    } catch (_) {
        value = `${Date.now()}-${Math.random().toString(36).slice(2, 14)}`;
    }
    return `${prefix}.${value}`.slice(0, 64);
}

export function getAnalyticsSessionId() {
    try {
        let value = sessionStorage.getItem(SESSION_KEY);
        if (!value) {
            value = newClientId('ses');
            sessionStorage.setItem(SESSION_KEY, value);
        }
        return value;
    } catch (_) {
        if (!window.__geoAnalyticsSessionId) {
            window.__geoAnalyticsSessionId = newClientId('ses');
        }
        return window.__geoAnalyticsSessionId;
    }
}

export function createActionContext(runMode, triggerOrigin) {
    return {
        run_mode: runMode,
        trigger_origin: triggerOrigin,
        client_session_id: getAnalyticsSessionId(),
        client_action_id: newClientId('act'),
    };
}

export function resultTrackingContext(result) {
    const taskTracking = window.currentGeocodingTracking || {};
    return {
        geocoding_task_id: taskTracking.task_id || null,
        address_log_id: result?.tracking_address_log_id || null,
        client_action_id: taskTracking.client_action_id || null,
    };
}

export function correctionMetadata(result, selectionMethod, correctionSource) {
    const selected = result?.selected_result || {};
    const details = selected.result || {};
    return {
        address_index: Number.isInteger(result?.tracking_address_index)
            ? result.tracking_address_index
            : undefined,
        previous_source: result?.api_results?.find(item => item?.selected)?.api || undefined,
        final_source: selected.api || selected.source_api || undefined,
        selection_method: selectionMethod,
        correction_source: correctionSource,
        confidence_after: typeof selected.confidence === 'number' ? selected.confidence : undefined,
        latitude_wgs84: typeof details.latitude_wgs84 === 'number' ? details.latitude_wgs84 : undefined,
        longitude_wgs84: typeof details.longitude_wgs84 === 'number' ? details.longitude_wgs84 : undefined,
    };
}

export async function trackInteraction(eventName, options = {}) {
    const payload = {
        event_name: eventName,
        trigger_origin: options.triggerOrigin || 'unknown',
        button_id: options.buttonId || undefined,
        success: typeof options.success === 'boolean' ? options.success : undefined,
        metadata: options.metadata || {},
        client_event_id: newClientId('evt'),
        client_session_id: getAnalyticsSessionId(),
        client_action_id: options.clientActionId || undefined,
        geocoding_task_id: options.geocodingTaskId || undefined,
        address_log_id: options.addressLogId || undefined,
    };
    try {
        return await fetchAPI('/geocode/interaction_events', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
    } catch (error) {
        console.warn('交互事件记录失败:', eventName, error?.message || error);
        return null;
    }
}

export function trackButtonExposureOnce(buttonId, options = {}) {
    const taskKey = options.geocodingTaskId || 'page';
    const key = `${taskKey}:${buttonId}`;
    if (exposedButtons.has(key)) return;
    const element = document.getElementById(buttonId);
    if (!element || element.disabled || element.style.display === 'none') return;
    exposedButtons.add(key);
    trackInteraction('button_exposed', {
        ...options,
        triggerOrigin: options.triggerOrigin || 'system',
        buttonId,
    });
}
