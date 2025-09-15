import re
import Levenshtein
import jionlp as jio
from ..utils.location_loader import get_location_types_data
from flask import current_app

def remove_suffixes(address_text: str, suffixes_to_remove: list[str] = None) -> str:
    """
    从地址文本的末尾移除指定的后缀列表中的任何一个后缀。
    如果未提供 suffixes_to_remove，则使用 LOCATION_TYPES_DATA 中的后缀。
    """
    if not address_text:
        return address_text
    
    # 如果没有提供后缀列表，使用默认的
    actual_suffixes = suffixes_to_remove if suffixes_to_remove is not None else get_location_types_data()

    # 关键修复：必须按长度降序排序，以确保优先匹配并移除最长的后缀
    # 例如，对于"历史文化街区"，应先匹配"历史文化街区"而不是"街区"
    actual_suffixes.sort(key=len, reverse=True)

    if not actual_suffixes: # 如果仍然为空（例如，LOCATION_TYPES_DATA 为空）
        return address_text
    
    processed_text = address_text
    for suffix in actual_suffixes:
        if suffix and processed_text.endswith(suffix):
            processed_text = processed_text[:-len(suffix)]
            break 
    return processed_text

def extract_province_city(keyword):
    """
    这是一个简化的示例，您可能需要更复杂的逻辑
    例如使用正则表达式或地址解析库
    此处仅为占位符
    """
    return "", ""

def calculate_confidence_A(parsed_original_address: dict, candidate_result: dict) -> float:
    """
    A-类置信度计算模型 (基于文本相似度)。
    适用于高德地图。
    假定原始地址已被预处理和解析。
    
    @deprecated: 此函数已被弃用，请使用 calculate_unified_confidence(mode='geocoding') 代替。
    将在未来版本中移除。
    """
    if not parsed_original_address or not candidate_result or not isinstance(candidate_result, dict):
        return 0.0

    # SOP 7.1, Step 2: 行政区划硬性过滤 (直接对比)
    # 不再解析formatted_address, 而是直接使用高德返回的结构化字段
    
    # 省份对比
    if (parsed_original_address.get('province') or '').strip() != (candidate_result.get('province') or '').strip():
        return 0.0
    # 城市对比
    if (parsed_original_address.get('city') or '').strip() != (candidate_result.get('city') or '').strip():
        return 0.0
    
    # 区县条件性对比
    original_county = (parsed_original_address.get('county') or '').strip()
    # 注意: 高德返回的是 'district'
    candidate_district = (candidate_result.get('district') or '').strip() 
    if original_county and original_county != candidate_district:
        current_app.logger.debug(
            f"置信度审查失败 (区县不匹配): 原始区县='{original_county}', "
            f"候选区县='{candidate_district}'"
        )
        return 0.0

    # SOP 7.1, Step 3: 详细地址提取
    # 原始地址的detail
    detail_orig = (parsed_original_address.get('detail') or '').strip()
    # 候选地址的detail: 此时需要解析formatted_address来获取
    candidate_address_str = candidate_result.get('formatted_address')
    detail_cand = ''
    if candidate_address_str:
        try:
            # 仅为提取detail而解析
            parsed_candidate_for_detail = jio.parse_location(candidate_address_str.strip())
            detail_cand = (parsed_candidate_for_detail.get('detail') or '').strip()
        except Exception:
            # 解析失败时，使用'name'或'address'字段作为降级方案
            detail_cand = (candidate_result.get('name', '') or candidate_result.get('address', '')).strip()

    # SOP 7.1, Step 4: 核心地址提纯 (Suffix Removal)
    detail_orig_pure = remove_suffixes(detail_orig)
    detail_cand_pure = remove_suffixes(detail_cand)
    current_app.logger.debug(
        f"核心地址提纯: 原始='{detail_orig}' -> '{detail_orig_pure}', "
        f"候选='{detail_cand}' -> '{detail_cand_pure}'"
    )

    norm_detail_orig = _normalize_detail_for_confidence(detail_orig_pure)
    norm_detail_cand = _normalize_detail_for_confidence(detail_cand_pure)

    if not norm_detail_orig and not norm_detail_cand:
        return 1.0 # 如果两者详细地址都为空(例如只查一个区)，则认为完全匹配
    
    return Levenshtein.ratio(norm_detail_orig, norm_detail_cand)

def calculate_confidence_B(provider: str, result_dict: dict) -> float:
    """
    B-类置信度计算模型 (基于原生指标)。
    适用于百度地图和天地图。
    """
    if not provider or not result_dict or result_dict.get('error'):
        return 0.0

    if provider == 'baidu':
        # 使用标准化后的原生分数字段
        confidence = float(result_dict.get('native_confidence', 0))
        comprehension = float(result_dict.get('native_comprehension', 0))
        # SOP 公式: ((confidence + comprehension) / 2) / 100.0
        return ((confidence + comprehension) / 2.0) / 100.0
    
    elif provider == 'tianditu':
        # 使用标准化后的原生分数字段
        score = float(result_dict.get('native_score', 0))
        # SOP 公式: score / 100.0 (假设 score 是 0-100 制)
        return score / 100.0

    return 0.0

def _normalize_detail_for_confidence(text_input) -> str:
    if not text_input:
        return ""
    text = str(text_input) # 确保输入是字符串

    # 全角转半角
    normalized_chars = []
    for char_text in text:
        num = ord(char_text)
        if num == 0x3000:  # 全角空格
            num = 32
        elif 0xFF01 <= num <= 0xFF5E:  # 全角字符 (不包括空格)
            num -= 0xFEE0
        normalized_chars.append(chr(num))
    text = ''.join(normalized_chars)

    # 转为小写并移除所有空白符
    return re.sub(r'\s+', '', text.lower())

def generate_completed_address(parsed_address: dict) -> str:
    """
    根据jionlp解析出的地址字典，生成一个完整的、用于查询的地址字符串。
    它会智能地拼接省、市、县、乡镇和详细地址。
    """
    if not parsed_address:
        return ""

    # 按顺序提取地址组件
    province = parsed_address.get('province', '')
    city = parsed_address.get('city', '')
    county = parsed_address.get('county', '')
    # 乡镇信息可能在 'town' 或 'street' 字段
    town = parsed_address.get('town', '') or parsed_address.get('street', '') 
    detail = parsed_address.get('detail', '')

    # 开始拼接
    # 规则1: 省和市相同，保留一个 (例如 "北京市北京市" -> "北京市")
    if province == city:
        full_address = city
    else:
        full_address = province + city

    # 规则2: 避免重复添加区县
    # 如果地址详情已经包含了区县信息，就不再添加
    if county and county not in detail:
        full_address += county
    
    # 规则3: 避免重复添加乡镇
    if town and town not in detail:
        full_address += town

    full_address += detail
    
    # 移除可能由拼接产生的重复词（例如 "北京市海淀区海淀区中关村"）
    parts = list(filter(None, [province, city, county, town, detail]))
    unique_parts = []
    last_part = None
    for part in parts:
        if part != last_part:
            unique_parts.append(part)
        last_part = part

    # 最终使用优化过的拼接方式
    final_address = "".join(unique_parts)
    
    # 对于非常短的地址（比如只有一个区），最好还是用原始解析的拼接
    if len(final_address) < len(full_address):
        return full_address
        
    return final_address

def complete_address_jionlp(address: str, return_dict=False):
    """
    使用 jionlp 尝试补全单个地址的行政区划。
    如果补全成功，返回新地址；如果失败或输入不合法，返回原地址。
    可以根据 return_dict 参数决定返回字符串还是字典。
    """
    if not address or not isinstance(address, str):
        if return_dict:
            return {'completed_address': address, 'parsed_address': {}}
        return address
        
    try:
        # 使用 jionlp 解析地址
        parsed = jio.parse_location(address)
        
        # 检查是否包含最基本的省和市信息
        if parsed and parsed.get('province') and parsed.get('city'):
            completed_address = generate_completed_address(parsed)
            if return_dict:
                return {'completed_address': completed_address, 'parsed_address': parsed}
            return completed_address
        else:
            # 如果解析失败，保持原地址不变
            if return_dict:
                return {'completed_address': address, 'parsed_address': parsed or {}}
            return address
            
    except Exception as e:
        # 在实际应用中，这里应该有日志记录
        print(f"使用jionlp解析地址 '{address}' 时出错: {e}")
        # 解析失败时保持原地址
        if return_dict:
            return {'completed_address': address, 'parsed_address': {}}
        return address

def calculate_unified_confidence(
    original_address: str, 
    candidate_data: dict, 
    parsed_original: dict = None,
    mode: str = 'geocoding'
) -> float:
    """
    统一置信度计算函数，实现SOP中定义的融合匹配模型。
    
    Args:
        original_address: 原始地址字符串 (对应 Source-Full)
        candidate_data: 候选数据字典 (POI或Geocoding结果)
        parsed_original: 预解析的原始地址结构 (对应 Source-Detail)
        mode: 计算模式，'geocoding'或'poi'
    
    Returns:
        float: 置信度分数 (0.0 - 1.0)
    """
    if not original_address or not candidate_data:
        return 0.0
    
    # --- 步骤 0: 确保结构化查询存在 ---
    if parsed_original is None:
        # 降级方案：如果上游没有提供解析结果，则即时解析
        parsed_original = jio.parse_location(original_address)
    
    # --- 步骤 1: 行政区划硬性过滤 ---
    if not _check_administrative_match(parsed_original, candidate_data, mode):
        return 0.0
    
    # --- 步骤 2: 准备 "比较源" (Query Sources) ---
    # 源1: 查询详情 (Source-Detail)
    source_detail_raw = (parsed_original.get('detail') or '').strip()
    source_detail = _normalize_detail_for_confidence(remove_suffixes(source_detail_raw))
    # 源2: 查询全文 (Source-Full)
    source_full = _normalize_detail_for_confidence(remove_suffixes(original_address))

    # --- 步骤 3: 准备 "候选维度" & 执行计算策略 ---
    confidences = []

    def _get_candidate_details(text: str) -> str:
        """安全地解析候选文本并返回其标准化的detail部分"""
        if not text:
            return ""
        try:
            parsed = jio.parse_location(text)
            detail = (parsed.get('detail') or '').strip()
        except Exception:
            # 解析失败时，使用原始文本作为降级
            detail = text
        return _normalize_detail_for_confidence(remove_suffixes(detail))

    if mode == 'poi':
        # --- POI模式：执行融合策略 ---
        # 维度1: 候选名称
        cand_name_full_raw = (candidate_data.get('name') or '').strip()
        if cand_name_full_raw:
            # 补充维度: 候选名称全文 (Dim-Name-Full)
            cand_name_full = _normalize_detail_for_confidence(remove_suffixes(cand_name_full_raw))
            confidences.append(_calculate_text_similarity_with_containment(
                source_full, cand_name_full, "全文 vs POI名称全文"
            ))
            # 主要维度: 候选名称详情 (Dim-Name-Detail)
            cand_name_detail = _get_candidate_details(cand_name_full_raw)
            if cand_name_detail:
                 confidences.append(_calculate_text_similarity_with_containment(
                    source_detail, cand_name_detail, "详情 vs POI名称详情"
                ))

        # 维度2: 候选地址
        cand_addr_full_raw = (candidate_data.get('address') or '').strip()
        if cand_addr_full_raw:
            # 补充维度: 候选地址全文 (Dim-Address-Full)
            cand_addr_full = _normalize_detail_for_confidence(remove_suffixes(cand_addr_full_raw))
            confidences.append(_calculate_text_similarity_with_containment(
                source_full, cand_addr_full, "全文 vs POI地址全文"
            ))
            # 主要维度: 候选地址详情 (Dim-Address-Detail)
            cand_addr_detail = _get_candidate_details(cand_addr_full_raw)
            if cand_addr_detail:
                confidences.append(_calculate_text_similarity_with_containment(
                    source_detail, cand_addr_detail, "详情 vs POI地址详情"
                ))

    elif mode == 'geocoding':
        # --- 地理编码模式：执行简化策略 ---
        cand_addr_full_raw = (candidate_data.get('formatted_address') or '').strip()
        if cand_addr_full_raw:
            # 主要维度: 候选地址详情 (Dim-Address-Detail)
            cand_addr_detail = _get_candidate_details(cand_addr_full_raw)
            confidences.append(_calculate_text_similarity_with_containment(
                source_detail, cand_addr_detail, "详情 vs Geocoding地址详情"
            ))

    # --- 步骤 4: 选择最优结果 ---
    if not confidences:
        current_app.logger.warning(
            f"置信度计算无法进行有效比较, 模式='{mode}', 原始地址='{original_address}', "
            f"候选名称='{candidate_data.get('name', 'N/A')}', "
            f"候选地址='{candidate_data.get('address') or candidate_data.get('formatted_address', 'N/A')}'"
        )
        return 0.5  # 如果没有任何有效维度可以比较，返回一个中立的分数

    best_confidence = max(confidences)
    
    current_app.logger.debug(
        f"统一置信度计算: 模式='{mode}', 原始='{original_address}', "
        f"候选='{candidate_data.get('name', '')}', "
        f"比较分数列表={confidences}, 最终置信度={best_confidence:.3f}"
    )
    
    return best_confidence


def _check_administrative_match(parsed_original: dict, candidate_data: dict, mode: str) -> bool:
    """检查行政区划匹配，统一处理两种模式的字段差异"""
    
    # 省级匹配
    original_province = (parsed_original.get('province') or '').strip()
    if mode == 'geocoding':
        candidate_province = (candidate_data.get('province') or '').strip()
    else:  # poi
        candidate_province = (candidate_data.get('pname') or '').strip()
    
    if original_province and candidate_province and original_province != candidate_province:
        current_app.logger.debug(f"置信度过滤：省份不匹配 '{original_province}' vs '{candidate_province}'")
        return False
    
    # 市级匹配
    original_city = (parsed_original.get('city') or '').strip()
    if mode == 'geocoding':
        candidate_city = (candidate_data.get('city') or '').strip()
    else:  # poi
        candidate_city = (candidate_data.get('cityname') or '').strip()
    
    if original_city and candidate_city and original_city != candidate_city:
        current_app.logger.debug(f"置信度过滤：城市不匹配 '{original_city}' vs '{candidate_city}'")
        return False
    
    # 区县级条件匹配
    original_county = (parsed_original.get('county') or '').strip()
    if mode == 'geocoding':
        candidate_district = (candidate_data.get('district') or '').strip()
    else:  # poi
        candidate_district = (candidate_data.get('adname') or '').strip()
    
    if original_county and candidate_district and original_county != candidate_district:
        current_app.logger.debug(f"置信度过滤：区县不匹配 '{original_county}' vs '{candidate_district}'")
        return False
    
    return True


def _calculate_geocoding_confidence(parsed_original: dict, candidate_data: dict) -> float:
    """地理编码模式的置信度计算（原A-类模型逻辑）"""
    
    # 详细地址提取
    detail_orig = (parsed_original.get('detail') or '').strip()
    
    # 候选地址的detail
    candidate_address_str = candidate_data.get('formatted_address')
    detail_cand = ''
    if candidate_address_str:
        try:
            parsed_candidate = jio.parse_location(candidate_address_str.strip())
            detail_cand = (parsed_candidate.get('detail') or '').strip()
        except Exception:
            detail_cand = (candidate_data.get('name', '') or candidate_data.get('address', '')).strip()
    
    # 后缀移除和标准化
    detail_orig_pure = remove_suffixes(detail_orig)
    detail_cand_pure = remove_suffixes(detail_cand)
    
    norm_detail_orig = _normalize_detail_for_confidence(detail_orig_pure)
    norm_detail_cand = _normalize_detail_for_confidence(detail_cand_pure)
    
    current_app.logger.debug(
        f"地理编码置信度计算: 原始='{detail_orig}' -> '{detail_orig_pure}', "
        f"候选='{detail_cand}' -> '{detail_cand_pure}'"
    )
    
    if not norm_detail_orig and not norm_detail_cand:
        return 1.0
    
    # 应用包含关系增强算法
    return _calculate_text_similarity_with_containment(
        norm_detail_orig, norm_detail_cand, "地理编码地址"
    )


def _calculate_poi_confidence(parsed_original: dict, poi_data: dict, original_address: str) -> float:
    """
    POI模式的置信度计算，实现SOP中的多维度、双源匹配模型。
    - 多维度：同时评估POI的'name'和'address'字段。
    - 双源：同时使用原始查询的'全文'和解析出的'detail'核心词进行比较。
    """
    current_app.logger.debug(f"--- [CONFIDENCE_DEBUG] Calculating POI Confidence for POI: '{poi_data.get('name')}' ---")
    current_app.logger.debug(f"[CONFIDENCE_DEBUG] Original Query: '{original_address}'")
    
    # --- 双源匹配准备 ---
    # 源1: 解析后的核心部分 (e.g., "西山" from "绩溪县西山")
    detail_orig = (parsed_original.get('detail') or '').strip()
    detail_orig_pure = remove_suffixes(detail_orig)
    norm_detail_orig = _normalize_detail_for_confidence(detail_orig_pure)

    # 源2: 原始地址全文本 (e.g., "绩溪县西山")
    full_orig_pure = remove_suffixes(original_address)
    norm_full_orig = _normalize_detail_for_confidence(full_orig_pure)
    
    # --- 多维度匹配评估 ---
    confidences = []
    
    # 维度1: POI名称匹配
    poi_name = (poi_data.get('name') or '').strip()
    if poi_name:
        poi_name_pure = remove_suffixes(poi_name)
        norm_poi_name = _normalize_detail_for_confidence(poi_name_pure)
        if norm_poi_name:
            # 与 full address 比较
            confidences.append(_calculate_text_similarity_with_containment(
                norm_full_orig, norm_poi_name, "POI名称 vs 全文"
            ))
            # 与 detail 比较 (如果 detail 存在且与全文不同)
            if norm_detail_orig and norm_detail_orig != norm_full_orig:
                confidences.append(_calculate_text_similarity_with_containment(
                    norm_detail_orig, norm_poi_name, "POI名称 vs Detail"
                ))
    
    # 维度2: POI地址匹配  
    poi_address = (poi_data.get('address') or '').strip()
    if poi_address:
        try:
            # 同样只提取地址中的detail部分进行比较
            parsed_poi = jio.parse_location(poi_address)
            detail_poi = (parsed_poi.get('detail') or '').strip()
        except Exception:
            detail_poi = poi_address # 解析失败则使用全地址
        
        if detail_poi:
            detail_poi_pure = remove_suffixes(detail_poi)
            norm_detail_poi = _normalize_detail_for_confidence(detail_poi_pure)
            if norm_detail_poi:
                # 与 full address 比较
                confidences.append(_calculate_text_similarity_with_containment(
                    norm_full_orig, norm_detail_poi, "POI地址 vs 全文"
                ))
                # 与 detail 比较 (如果 detail 存在且与全文不同)
                if norm_detail_orig and norm_detail_orig != norm_full_orig:
                    confidences.append(_calculate_text_similarity_with_containment(
                        norm_detail_orig, norm_detail_poi, "POI地址 vs Detail"
                    ))
    
    # --- 选择最优结果 ---
    if not confidences:
        # 如果没有任何有效维度可以比较，返回一个中立的分数
        current_app.logger.warning(f"POI置信度计算无法进行有效比较，原始地址: '{original_address}', POI名称: '{poi_name}', POI地址: '{poi_address}'")
        return 0.5
    
    best_dimension, best_confidence = max(confidences, key=lambda x: x[1])
    
    current_app.logger.debug(
        f"POI多维度匹配: 原始='{original_address}', POI='{poi_name}', "
        f"比较详情={confidences}, 最佳维度='{best_dimension}', 最终置信度={best_confidence:.3f}"
    )
    current_app.logger.debug(f"--- [CONFIDENCE_DEBUG] END POI Confidence for POI: '{poi_data.get('name')}' ---")
    
    return best_confidence


def _calculate_text_similarity_with_containment(text1: str, text2: str, dimension_name: str) -> float:
    """
    计算两个文本的相似度，考虑包含关系的增强算法。
    
    Args:
        text1: 第一个文本（通常是原始地址）
        text2: 第二个文本（通常是POI名称或地址）
        dimension_name: 维度名称，用于日志
    
    Returns:
        相似度分数 (0.0 - 1.0)
    """
    current_app.logger.debug(f"[CONFIDENCE_DEBUG] Similarity Check ('{dimension_name}'): '{text1}' vs '{text2}'")
    if not text1 and not text2:
        return 1.0
    
    if not text1 or not text2:
        return 0.5
    
    # 基础编辑距离相似度
    base_similarity = Levenshtein.ratio(text1, text2)
    current_app.logger.debug(f"[CONFIDENCE_DEBUG]   -> Base Levenshtein Ratio: {base_similarity:.3f}")
    
    # 包含关系增强
    enhanced_similarity = base_similarity
    
    if text1 in text2:
        # text1包含在text2中，如"迁江老街"在"迁江老街米粉"中
        # 这种情况通常表示用户搜索地名，POI是该地名的具体商户，匹配度应该很高
        contain_ratio = len(text1) / len(text2)
        
        # 改进算法：基线更高，但增长更平缓
        if contain_ratio >= 0.8:
            # 几乎完全匹配，如"迁江老街" vs "迁江老街店"
            enhanced_similarity = max(base_similarity, 0.95 + contain_ratio * 0.05)  # 95%-100%
        elif contain_ratio >= 0.5:
            # 高度匹配，如"迁江老街" vs "迁江老街米粉"
            enhanced_similarity = max(base_similarity, 0.90 + contain_ratio * 0.10)  # 90%-95%
        else:
            # 中等匹配，如"迁江老街" vs "迁江老街米粉餐厅连锁店"
            enhanced_similarity = max(base_similarity, 0.80 + contain_ratio * 0.20)  # 80%-90%
            
        current_app.logger.debug(
            f"{dimension_name}包含关系A: '{text1}' in '{text2}', 长度比例={contain_ratio:.3f}, 基础相似度={base_similarity:.3f}, 增强置信度={enhanced_similarity:.3f}"
        )
    elif text2 in text1:
        # text2包含在text1中，如"米粉店" in "广西来宾市迁江老街米粉店"
        # 这种情况表示POI名称是用户搜索的一部分，需要谨慎评分
        contain_ratio = len(text2) / len(text1)
        
        # 更加保守的评分策略，因为POI名称可能过于泛化
        if len(text2) >= 4 and contain_ratio >= 0.3:
            # POI名称足够具体且占比合理，如"迁江老街米粉" in "迁江老街米粉店"
            enhanced_similarity = max(base_similarity, 0.75 + contain_ratio * 0.20)  # 75%-95%
        elif len(text2) >= 3 and contain_ratio >= 0.2:
            # POI名称中等具体，如"米粉店" in "迁江老街米粉店"
            enhanced_similarity = max(base_similarity, 0.65 + contain_ratio * 0.20)  # 65%-85%
        else:
            # POI名称太短或占比太小，如"店" in "迁江老街米粉店"，可能是泛化词汇
            enhanced_similarity = max(base_similarity, 0.50 + contain_ratio * 0.25)  # 50%-75%
            
        current_app.logger.debug(
            f"{dimension_name}包含关系B: '{text2}' in '{text1}', 长度比例={contain_ratio:.3f}, POI长度={len(text2)}, 基础相似度={base_similarity:.3f}, 增强置信度={enhanced_similarity:.3f}"
        )
    else:
        current_app.logger.debug(
            f"{dimension_name}基础相似度: '{text1}' vs '{text2}' = {base_similarity:.3f}"
        )
    
    current_app.logger.debug(f"[CONFIDENCE_DEBUG]   -> Final Enhanced Similarity for '{dimension_name}': {enhanced_similarity:.3f}")
    return enhanced_similarity