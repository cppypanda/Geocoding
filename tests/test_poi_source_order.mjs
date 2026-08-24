import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const smartCalibration = await readFile(new URL('../static/js/modules/smart-calibration.js', import.meta.url), 'utf8');
const template = await readFile(new URL('../app/templates/index.html', import.meta.url), 'utf8');
const apiModule = await readFile(new URL('../static/js/modules/api.js', import.meta.url), 'utf8');
const calibrationModule = await readFile(new URL('../static/js/modules/calibration.js', import.meta.url), 'utf8');
const backendRoute = await readFile(new URL('../app/routes/geocoding.py', import.meta.url), 'utf8');

assert.match(
    smartCalibration,
    /const poiSources = \['baidu', 'tianditu', 'amap'\]/,
    'automatic POI fallback must use Baidu, Tianditu, Amap order',
);
assert.match(
    smartCalibration,
    /setSelectValue\('#map-search-source', 'baidu'\)/,
    'keyword fallback must default to Baidu',
);

const baiduOption = template.indexOf('<option value="baidu" selected>百度</option>');
const tiandituOption = template.indexOf('<option value="tianditu">天地图</option>');
const amapOption = template.indexOf('<option value="amap">高德</option>');
assert.ok(baiduOption >= 0, 'Baidu must be the selected page default');
assert.ok(baiduOption < tiandituOption && tiandituOption < amapOption, 'page options must follow Baidu, Tianditu, Amap order');
assert.match(apiModule, /performMapSearch\(searchTerm, source = 'baidu'\)/, 'frontend API fallback must default to Baidu');
assert.match(calibrationModule, /handleMapSearch\(searchTerm, source = 'baidu'/, 'calibration fallback must default to Baidu');
assert.match(backendRoute, /data\.get\('source', 'baidu'\)/, 'backend POI fallback must default to Baidu');

console.log('POI source order tests passed');
