/**
 * Decide whether a cascade-result row needs smart calibration.
 * Missing or malformed confidence means that the geocoding pipeline did not
 * produce a trustworthy result, so it must be included in the fallback flow.
 */
export function shouldCalibrateConfidence(confidenceText) {
    const normalized = confidenceText == null ? '' : String(confidenceText).trim();
    if (!normalized || normalized === '-' || normalized === '—') {
        return true;
    }

    const confidence = Number.parseFloat(normalized.replace('%', ''));
    return !Number.isFinite(confidence) || confidence < 90;
}
