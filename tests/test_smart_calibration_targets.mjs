import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const moduleUrl = new URL('../static/js/modules/smart-calibration-targets.js', import.meta.url);
const source = await readFile(moduleUrl, 'utf8');
const targetModule = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const { shouldCalibrateConfidence } = targetModule;

assert.equal(shouldCalibrateConfidence('-'), true, 'missing result must enter fallback');
assert.equal(shouldCalibrateConfidence(''), true, 'empty confidence must enter fallback');
assert.equal(shouldCalibrateConfidence(undefined), true, 'undefined confidence must enter fallback');
assert.equal(shouldCalibrateConfidence('invalid'), true, 'malformed confidence must enter fallback');
assert.equal(shouldCalibrateConfidence('50.0%'), true, 'low confidence must enter fallback');
assert.equal(shouldCalibrateConfidence('89.9%'), true, 'confidence below threshold must enter fallback');
assert.equal(shouldCalibrateConfidence('90.0%'), false, 'threshold confidence must be accepted');
assert.equal(shouldCalibrateConfidence('95.0%'), false, 'high confidence must be accepted');

console.log('smart calibration target tests passed');
