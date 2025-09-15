import json
import re
import asyncio
import traceback
from datetime import datetime
from flask import current_app

SMART_SEARCH_PROMPT = '''请分析以下搜索关键词，并以JSON格式返回相关的地理位置信息：
{query}

请按照以下格式返回结果：
{{
    "locations": [
        {{
            "name": "地点名称",
            "address": "完整地址",
            "description": "位置说明",
            "type": "地点类型",
            "confidence": 0.95
        }}
    ]
}}

要求：
1. 每个地点必须包含以上所有字段
2. name字段应该是最具体的地点名称
3. address字段应该包含完整的地址信息
4. description字段应该说明该地点与搜索词的关系
5. type字段应该说明地点的类型（如公司、学校、商场等）
6. confidence字段表示该地点与搜索词的匹配程度

请确保返回的是合法的JSON格式。'''

async def call_zhipu_web_enabled_llm(original_query_address: str, max_retries: int = 3):
    """使用智谱AI的联网搜索功能来搜索地址相关信息"""
    client = current_app.extensions.get('zhipuai_client')
    if not client:
        return {
            "error": "ZhipuAI client not initialized. Please check ZHIPUAI_KEY.",
            "llm_output": "智谱AI客户端未初始化",
            "web_search_results_count": 0,
            "web_search_references": [],
            "request_timestamp": datetime.now().isoformat(),
            "response_timestamp": datetime.now().isoformat()
        }

    try:
        search_response = client.web_search.web_search(
            search_engine="search-pro",
            search_query=original_query_address
        )
        
        if not search_response or not search_response.search_result:
            return {
                "llm_output": "未能获取到有效的搜索结果",
                "web_search_results_count": 0,
                "web_search_references": [],
                "request_timestamp": datetime.now().isoformat(),
                "response_timestamp": datetime.now().isoformat(),
                "error": "无搜索结果"
            }

        search_context = "\n\n".join([
            f"来源：{result.media if result.media else '未知来源'}\n{result.content}"
            for result in search_response.search_result if result.content
        ])

        main_prompt = f'''
原始地址为：{original_query_address}，在网络地图上无法找到原始地址的位置，现在在网页上收集地址的相关信息，提取可能在反映地址位置的其他地点。

{search_context}
相关地点可以考虑原始地址的详细地址、范围、内部地点、相邻地点等。

请找出所有确实能反映原始地址位置的地点（且除去与原始地址字面相同的地点），并按要求的先后顺序列出条目，如果搜索结果中未提供反映原始地址的地点，请直接回复"无相关地点信息"，如果有，按照以下格式返回结果：

地点条目示例格式(N代表序号)：
N. 地点：地点名称（可以是单个或多个，多个地点用顿号、逗号分隔）
   关系：与主要地点的关系说明

不限制条目数量，条目最可能通过网络地图准确搜索到的顺序排列（微观到宏观），可考虑按原始地址内部或相同位置在前、相邻位置和其他位置在后排列（在最后说明原因）。

行政区：xx省xx市xx县（以上所有地点所在的行政区域）

说明：前面条目如此列先后的理由。
'''
        print(main_prompt)
        llm_response = await asyncio.to_thread(
            client.chat.completions.create,
            model="glm-4-flash",
            messages=[{"role": "user", "content": main_prompt}],
            stream=False,
            max_tokens=4090
        )

        if not llm_response.choices or not llm_response.choices[0].message:
            web_search_references = []
            for r in search_response.search_result:
                if hasattr(r, 'refer') and r.refer:
                    web_search_references.append(r.refer)
                    
            return {
                "llm_output": "大模型未能生成有效回复",
                "web_search_results_count": len(search_response.search_result),
                "web_search_references": web_search_references,
                "request_timestamp": datetime.now().isoformat(),
                "response_timestamp": datetime.now().isoformat(),
                "error": "LLM响应无效"
            }

        web_search_references = []
        for r in search_response.search_result:
            if hasattr(r, 'refer') and r.refer:
                web_search_references.append(r.refer)
        
        return {
            "llm_output": llm_response.choices[0].message.content.strip(),
            "web_search_results_count": len(search_response.search_result),
            "web_search_references": web_search_references,
            "request_timestamp": datetime.now().isoformat(),
            "response_timestamp": datetime.now().isoformat(),
            "error": None
        }

    except Exception as e:
        print(f"联网搜索出错: {str(e)}")
        traceback.print_exc()
        return {
            "llm_output": f"联网搜索过程中发生错误: {str(e)}",
            "web_search_results_count": 0,
            "web_search_references": [],
            "request_timestamp": datetime.now().isoformat(),
            "response_timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

async def call_llm_api(prompt, max_retries=3):
    """调用智谱AI的API，并返回包含时间戳和内容的字典"""
    client = current_app.extensions.get('zhipuai_client')
    llm_req_ts = None
    llm_res_ts = None
    
    try:
        if not client:
            print("智谱AI客户端未初始化，请检查API密钥配置")
            return {
                'content': None,
                'request_timestamp': None,
                'response_timestamp': datetime.now().isoformat(),
                'error': "智谱AI客户端未初始化"
            }
            
        for attempt in range(max_retries):
            try:
                llm_req_ts = datetime.now().isoformat()
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model="glm-4-flash",
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一个地理位置分析专家，请基于用户的提示词判断地址匹配程度。"
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )
                llm_res_ts = datetime.now().isoformat()
                
                if not response or not response.choices:
                    error_msg = f"API响应格式错误 (尝试 {attempt + 1}/{max_retries})"
                    print(error_msg)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                    return {
                        'content': None,
                        'request_timestamp': llm_req_ts, 
                        'response_timestamp': llm_res_ts, 
                        'error': error_msg
                    }
                
                return {
                    'content': response.choices[0].message.content,
                    'request_timestamp': llm_req_ts,
                    'response_timestamp': llm_res_ts,
                    'error': None 
                }
                    
            except Exception as e:
                llm_res_ts = datetime.now().isoformat() 
                error_msg = f"API调用出错 (尝试 {attempt + 1}/{max_retries}): {str(e)}"
                print(error_msg)
                traceback.print_exc() 
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return {
                    'content': None,
                    'request_timestamp': llm_req_ts, 
                    'response_timestamp': llm_res_ts,
                    'error': error_msg
                }
                
    except Exception as e:
        final_error_msg = f"调用智谱AI API函数时发生严重内部错误: {str(e)}"
        print(final_error_msg)
        traceback.print_exc()
        return {
            'content': None,
            'request_timestamp': llm_req_ts, 
            'response_timestamp': datetime.now().isoformat(), 
            'error': final_error_msg
        }

def get_llm_suggestions(search_results, original_address):
    """使用LLM生成搜索建议"""
    try:
        context = "以下是搜索结果的全文：\n\n"
        for i, result in enumerate(search_results[:5], 1):
            context += f"{i}. {result.get('标题', '')}\n"
            content = result.get('文章内容', '') if result.get('文章内容') else result.get('简介', '')
            context += f"   {content}\n\n"
            
        prompt = f"""在网络地图上无法找到{original_address}位置，现在在网页上收集地址的相关信息，提取可能在反映地址位置的其他地点。

{context}
相关地点可以考虑{original_address}的详细地址、范围、内部地点、相邻地点等。

请列出所有确实能反映{original_address}位置的地点（且除去与"{original_address}"字面相同的地点），如果搜索结果中未提供反映{original_address}位置的地点，请直接回复"无相关地点信息"，如果有，按照以下格式返回结果：

地点条目示例格式(N代表序号)：
N. 地点：地点名称（可以是单个或多个，多个地点用顿号、逗号分隔）
   关系：与主要地点的关系说明

不限制条目数量，按照反映{original_address}位置的程度从大到小排列。

行政区：xx省xx市xx县（以上所有地点所在的行政区域）
"""

        print("\n=== 发送给LLM的提示词 ===")
        print(prompt)

        # Call the async function using asyncio.run or from an async context
        # For now, we will assume this is called from a context that can await
        response_dict = asyncio.run(call_llm_api(prompt))
        
        result = response_dict.get('content')
        if response_dict.get('error'):
            print(f"LLM调用失败: {response_dict['error']}")
            return "未找到相关地址信息"

        print("\n=== LLM的回复 ===")
        print(result)
        return result
        
    except Exception as e:
        print(f"\n=== 生成建议时出错 ===\n{str(e)}")
        return "未找到相关地址信息"

async def verify_address_match(original_address, geocoded_result):
    """使用LLM判断地理编码结果是否与原始地址匹配"""
    try:
        if not geocoded_result or not isinstance(geocoded_result, dict):
            print(f"无效的地理编码结果: {geocoded_result}")
            return {
                "match": False,
                "level": 1,
                "response": "地理编码结果无效或为空"
            }
            
        formatted_address = geocoded_result.get('formatted_address')
        if not formatted_address:
            print("地理编码结果缺少格式化地址")
            return {
                "match": False,
                "level": 1,
                "response": "地理编码结果缺少格式化地址"
            }

        context = f"""请判断以下两个地址是否指向同一个地点：

原始地址：{original_address}
地图服务返回的地址：{formatted_address}

请严格按照以下格式回复：

匹配度：[1-5]（1为不匹配，5为高度匹配）
理由：简短说明原因"""

        response_dict = await call_llm_api(context)
        if not response_dict or response_dict.get('error'):
            error_msg = response_dict.get('error', 'LLM调用未知错误') if response_dict else 'LLM调用失败'
            return {
                "match": False,
                "level": 1,
                "response": f"LLM调用失败: {error_msg}"
            }

        response = response_dict.get('content', '')
        lines = response.strip().split('\n')
        try:
            level = 1
            explanation = "未提供解释"
            
            for line in lines:
                line = line.strip()
                if line.startswith('匹配度：'):
                    level_str = ''.join(filter(str.isdigit, line))
                    if level_str:
                        level = int(level_str)
                        if level < 1 or level > 5:
                            print(f"匹配等级超出范围(1-5): {level}")
                            level = 1
                elif line.startswith('理由：'):
                    explanation = line[3:].strip()
            
            return {
                "match": level >= 4,
                "level": level,
                "response": explanation
            }
        except (ValueError, IndexError) as e:
            print(f"解析LLM响应失败: {str(e)}")
            print(f"原始响应: {response}")
            return {
                "match": False,
                "level": 1,
                "response": "解析LLM响应失败"
            }

    except Exception as e:
        print(f"地址匹配判断错误: {str(e)}")
        traceback.print_exc()
        return {
            "match": False,
            "level": 1,
            "response": f"判断过程出错: {str(e)}"
        }

def parse_llm_order_and_reason(response):
    """解析大模型返回的有无、顺序和理由"""
    presence = ''
    order = ''
    reason = ''
    if not response:
        return presence, order, reason
    
    presence_match = re.search(r'有无[:：]\s*(.*?)(?:\n|$)', response)
    order_match = re.search(r'顺序[:：]\s*(.*?)(?:\n|$)', response)
    reason_match = re.search(r'理由[:：]\s*(.*)', response)
    
    if presence_match:
        presence = presence_match.group(1).strip()
    if order_match:
        order = order_match.group(1).strip().replace('；', '').replace(';', '')
    if reason_match:
        reason = reason_match.group(1).strip()
    return presence, order, reason

def parse_llm_suggested_locations(llm_output_str: str) -> list[str]:
    suggestions = []
    if not llm_output_str or "无相关地点信息" in llm_output_str :
        return suggestions
    
    lines = llm_output_str.replace('\n', '\n').split('\n')
    
    for line in lines:
        match = re.search(r"(?:\\d+\\.\\s*)?地点：(.+)", line)
        if match:
            location_names_str = match.group(1).strip()
            
            location_names_str = re.sub(r"\\s*\\([^)]*\\)", "", location_names_str)
            
            names = [name.strip() for name in re.split(r"[、，,]", location_names_str) if name.strip()]
            suggestions.extend(names)
            
    return list(dict.fromkeys(suggestions))

async def select_best_poi_from_search(original_address: str, poi_results: list, user_id: int, source_context: str) -> dict:
    """
    使用LLM（通用代表性模板）从POI搜索结果中选择代表性最强的一项。
    仅当返回的 confidence ≥ 0.90 且 decision=index 时才采纳；否则返回错误用于回退。
    """
    if not poi_results:
        return {'error': 'POI结果列表为空，无法进行决策。'}

    # 注：不再做“街道名必须字面匹配”的机械校验，统一由模型+阈值+need_web_info 控制回退

    # 组织候选清单（尽量提供 name/address/type/admin）
    cand_lines = []
    for i, p in enumerate(poi_results):
        name = (p.get('name') or '').replace('\n', ' ').strip()
        addr = (p.get('address') or '').replace('\n', ' ').strip()
        ptype = (p.get('type') or p.get('level') or '').strip()
        province = p.get('pname') or p.get('province') or ''
        city = p.get('cityname') or p.get('city') or ''
        district = p.get('adname') or p.get('district') or ''
        admin = f"{province}{city}{district}"
        cand_lines.append(
            f"{{\"index\":{i},\"name\":\"{name}\",\"address\":\"{addr}\",\"type\":\"{ptype}\",\"admin\":\"{admin}\"}}"
        )
    cands_json_like = ",\n  ".join(cand_lines)

    # 通用系统提示（一次调用，允许 abstain）
    system_prompt = (
        '你是“地理地址-POI 匹配验证官”，你的核心职责是进行严格的、基于证据的验证。'
        '你的任务是分级决策：首先，尝试验证是否存在一个【完全等价】的POI。如果不存在，则在有充分理由的情况下，审慎地选择一个能【最大程度代表】用户意图的POI。如果连代表性POI都找不到，则必须弃权。\n\n'
        '**核心指令：**\n'
        '1.  **严守证据**: 绝对禁止任何主观猜测、常识推断。只使用输入信息。\n'
        '2.  **分级决策**: 你的任务不是简单地“找一个最像的”，而是根据证据的强度进行分级判断。\n'
        '3.  **高标准置信度**: 只有在满足【所有】硬性匹配标准时，置信度才能超过 0.9。\n\n'
        '**硬性匹配标准 (置信度 > 0.9 的【必要条件】):**\n'
        '*   **行政区划必须完全匹配**: 省、市、区县必须一致。\n'
        '*   **核心名称必须高度相关**: \n'
        '    *   A) 目标地址的核心名称【完全包含】在 POI 的名称或地址中。\n'
        '    *   B) 或，POI 名称【完全包含】在目标地址的核心名称中，且 POI 类型与目标地址类别相符。\n'
        '*   **类别必须兼容**: 目标地址描述的是一个建筑物，POI 不能是一条路或一个地区。反之亦然。\n\n'
        '**中等置信度代表点标准 (置信度 0.6-0.89 的【选择条件】):**\n'
        '*   **主次实体判断**: 当目标地址包含多个地名时（如 A—B），如果候选POI中有一个与主要地名（通常是第一个）完全匹配，且行政区划一致，你可以选择它作为代表点。\n'
        '*   **别名或简称**: 当目标地址可能是某个POI的别名或不完整名称时，如果POI的类型和位置能提供强有力的旁证，你可以选择它。\n'
        '*   **明确陈述局限性**: 在选择中等置信度代表点时，必须在 `reasons` 字段中明确说明这是一个代表性选择，并指出输入中的哪个部分未被完全匹配。例如：“选择‘留犊祠巷’作为主要代表，但用户的输入‘状元巷’部分在当前POI列表中未被匹配。”\n\n'
        '**决策背景**\n'
        '如果没有任何一个POI能满足高或中等置信度标准，就必须【弃权 (abstain)】。系统后续会自动通过网络搜索等方式处理这些弃权的地址。\n\n'
        '**输出格式:** 严格按照用户提供的 JSON 格式输出。在 `reasons` 字段中清晰陈述你的验证逻辑。'
    )

    user_prompt = f"""
目标: "{original_address}"
来源上下文: "{source_context}"

候选POI（index从0开始）:
[
  {cands_json_like}
]

仅输出严格JSON：
{{
  "decision": "index" | "abstain",
  "selected_index": <int or null>,
  "reasons": ["一条简洁、可核验的理由"],
  "confidence": 0.0-1.0
}}
"""

    # 调用 LLM
    llm_response = await call_llm_api(system_prompt + "\n\n" + user_prompt)
    current_app.logger.info(f"LLM 原始响应: {llm_response.get('content')}") # 增加原始响应日志
    if llm_response.get('error') or not llm_response.get('content'):
        return {'error': f"LLM API调用失败: {llm_response.get('error', '无有效内容返回')}"}

    # 解析响应（兼容新老两种格式）
    try:
        llm_json_content = llm_response['content']
        m = re.search(r"```json\s*([\s\S]+?)\s*```", llm_json_content)
        json_str = m.group(1) if m else llm_json_content
        data = json.loads(json_str)

        # 新模板
        if isinstance(data, dict) and 'decision' in data:
            decision = (data.get('decision') or '').strip()
            index = data.get('selected_index')
            confidence = float(data.get('confidence') or 0.0)
            reasons = data.get('reasons') or []

            # 优先采纳有效的选择
            if decision == 'index' and isinstance(index, int) and 0 <= index < len(poi_results) and confidence >= 0.60:
                selected_tmp = poi_results[index].copy()
                selected_tmp['llm_reason'] = (reasons[0] if reasons else '高置信度代表点')
                selected_tmp['llm_confidence'] = confidence
                selected_tmp['selected_index'] = index
                return selected_tmp
            
            # 否则，视为低置信度或弃权
            return {'error': 'NO_HIGH_CONFIDENCE', 'reasons': reasons}

        # 兼容旧模板
        best_index = data.get('best_match_index')
        conf = float(data.get('confidence') or 0.0)
        if isinstance(best_index, int) and 0 <= best_index < len(poi_results) and conf >= 0.60:
            selected_poi_temp = poi_results[best_index].copy()
            selected_poi_temp['llm_reason'] = data.get('reason', '')
            selected_poi_temp['llm_confidence'] = conf
            selected_poi_temp['selected_index'] = best_index
            return selected_poi_temp

        return {'error': 'NO_HIGH_CONFIDENCE'}

    except Exception as e:
        current_app.logger.error(f"解析/处理LLM响应失败: {e}\n原始响应: {llm_response.get('content')}")
        return {'error': '解析LLM响应失败，格式不正确。'}


async def validate_poi_with_dossier(original_address: str, poi_candidates: list, dossier: dict, max_bg_items: int = 12) -> dict:
    """
    使用LLM结合第一步的情报摘录，判断POI候选是否与原始地址匹配，并返回结构化决策。

    返回字段：
    {
      'has_match': bool,
      'best_match_index': int | None,
      'match_confidence': float,
      'validation_reason': str,
      'mismatch_reasons': list[str]
    }
    """
    try:
        # 1) 组织候选列表文本
        cand_lines = []
        for i, p in enumerate(poi_candidates):
            name = (p.get('name') or '').strip()
            addr = (p.get('address') or '').strip()
            province = p.get('pname') or p.get('province') or ''
            city = p.get('cityname') or p.get('city') or ''
            district = p.get('adname') or p.get('district') or ''
            cand_lines.append(f"{i}. 名称: {name} | 地址: {addr} | 行政区: {province}{city}{district}")

        cands_str = "\n".join(cand_lines)

        # 2) 组织情报背景文本
        excerpts = []
        try:
            items = (dossier or {}).get('collated_excerpts') or []
            for it in items[:max_bg_items]:
                ex = (it.get('excerpt') or '').strip()
                if ex:
                    excerpts.append(f"- {ex}")
        except Exception:
            pass
        bg_str = "\n".join(excerpts) if excerpts else '（无）'

        prompt = f"""
任务：综合“原始地址”和“背景情报摘录”，判断候选POI哪一项与原始地址最匹配。

原始地址：{original_address}

背景情报摘录（可能包含位置/范围/相邻地标/道路/河流等信息）：
{bg_str}

候选POI列表：
{cands_str}

请输出一个JSON对象，字段如下：
{{
  "has_match": <布尔，是否存在匹配项>,
  "best_match_index": <整数或-1，若无匹配填-1>,
  "match_confidence": <0到1之间的小数，置信度>,
  "validation_reason": "你做出判断的关键依据（引用上面的情报要点/行政区/邻接元素对照）",
  "mismatch_reasons": ["当无匹配时，列出不匹配的关键原因，多条可列"]
}}

注意：
- 充分利用“背景情报摘录”中的范围、相邻地标（如渡口/桥/街/路/河）与行政区层级来对照候选POI；
- 如果多个候选都不符，设置 has_match=false, best_match_index=-1，并给出 mismatch_reasons；
- 若能判断出匹配项，请给出明确的 best_match_index 和简洁充分的 validation_reason。
"""

        resp = await call_llm_api(prompt)
        if not resp or resp.get('error'):
            return {
                'has_match': False,
                'best_match_index': None,
                'match_confidence': 0.0,
                'validation_reason': f"LLM失败: {resp.get('error') if resp else '未知'}",
                'mismatch_reasons': ["LLM调用失败"]
            }

        content = (resp.get('content') or '').strip()

        # 尝试从markdown代码块中抽JSON
        m = re.search(r"```json\s*([\s\S]+?)\s*```", content)
        json_str = m.group(1) if m else content
        try:
            data = json.loads(json_str)
            has_match = bool(data.get('has_match', False))
            best_idx = data.get('best_match_index')
            conf = float(data.get('match_confidence') or 0.0)
            reason = data.get('validation_reason') or ''
            mismatch = data.get('mismatch_reasons') or []
            if has_match and (best_idx is None or not isinstance(best_idx, int) or best_idx < 0 or best_idx >= len(poi_candidates)):
                # 防御：索引无效则改为无匹配
                has_match = False
                best_idx = None
                conf = 0.0
                mismatch = ["返回了无效的索引"]
            return {
                'has_match': has_match,
                'best_match_index': best_idx,
                'match_confidence': conf,
                'validation_reason': reason,
                'mismatch_reasons': mismatch
            }
        except Exception:
            # 解析失败
            return {
                'has_match': False,
                'best_match_index': None,
                'match_confidence': 0.0,
                'validation_reason': '解析LLM响应失败',
                'mismatch_reasons': ['LLM响应不是有效JSON']
            }
    except Exception as e:
        traceback.print_exc()
        return {
            'has_match': False,
            'best_match_index': None,
            'match_confidence': 0.0,
            'validation_reason': f'内部错误: {str(e)}',
            'mismatch_reasons': ['内部错误']
        }

async def batch_semantic_analysis(addresses: list, max_sample_size: int = 10) -> dict:
    """
    批量语义预分析功能 - 根据SOP_Intelligent_Entity_Resolution.md Part A实现
    
    :param addresses: 地址列表
    :param max_sample_size: 最大抽样数量，默认10条
    :return: 包含主题名称、是否需要搜索、搜索查询等的字典
    """
    if not addresses:
        return {
            'theme_name': '未命名任务',
            'search_needed': False,
            'search_query': None,
            'error': '地址列表为空'
        }
    
    try:
        # 1. 智能抽样
        sample_addresses = _smart_sample_addresses(addresses, max_sample_size)
        
        # 2. 初步分析与自我评估 (Fast Path)
        initial_prompt = f"""请分析以下地址列表，并以JSON格式返回结果。结果需包含三个字段:
1. `theme_name`: (string) 你根据现有知识得出的任务主题名称（尽量具体，如增加省份、批次等信息等）。
2. `search_needed`: (boolean) 你是否需要通过网络搜索来更准确地理解这些地址的共同主题和空间尺度特性？如果你对实体类型（如'桑基鱼塘系统'）感到陌生或不确定，请设为 `true`。
3. `search_query`: (string, 可选) 如果 `search_needed` 为 `true`，请提供一个最优的、用于网络搜索的关键词。

地址列表：
{chr(10).join([f"{i+1}. {addr}" for i, addr in enumerate(sample_addresses)])}

请确保返回的是合法的JSON格式。"""

        initial_response = await call_llm_api(initial_prompt)
        
        if initial_response.get('error') or not initial_response.get('content'):
            current_app.logger.warning(f"语义预分析 Fast Path 失败: {initial_response.get('error', '无响应')} (使用默认主题)")
            return {
                'theme_name': '地理编码任务',
                'search_needed': False,
                'search_query': None,
                'error': f"初步分析失败: {initial_response.get('error', '无响应')}"
            }
        
        # 解析初步分析结果
        try:
            content = initial_response['content'].strip()
            # 尝试从Markdown代码块中提取JSON
            json_match = re.search(r'```json\s*([\s\S]+?)\s*```', content)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content
            
            initial_analysis = json.loads(json_str)
            
            # 验证必要字段
            theme_name = initial_analysis.get('theme_name', '地理编码任务')
            search_needed = initial_analysis.get('search_needed', False)
            search_query = initial_analysis.get('search_query')
            current_app.logger.info(
                f"语义预分析 Fast Path: theme_name='{theme_name}', search_needed={search_needed}, search_query='{search_query}'"
            )
            
        except json.JSONDecodeError as e:
            print(f"解析初步分析JSON失败: {e}")
            print(f"原始响应: {content}")
            current_app.logger.warning(f"语义预分析 Fast Path: JSON解析失败: {str(e)} (使用默认主题)")
            return {
                'theme_name': '地理编码任务',
                'search_needed': False,
                'search_query': None,
                'error': f"JSON解析失败: {str(e)}"
            }
        
        # 3. 条件性网络搜索 (Slow Path)
        if search_needed and search_query:
            try:
                current_app.logger.info(f"语义预分析 Slow Path: 开始联网搜索，search_query='{search_query}'")
                # 使用现有的联网搜索功能
                search_result = await call_zhipu_web_enabled_llm(search_query, max_retries=2)
                
                if search_result.get('error') or not search_result.get('llm_output'):
                    current_app.logger.warning(
                        f"语义预分析 Slow Path: 联网搜索失败: {search_result.get('error')} (回退Fast Path)"
                    )
                    # 如果网络搜索失败，返回初步分析结果
                    return {
                        'theme_name': theme_name,
                        'search_needed': search_needed,
                        'search_query': search_query,
                        'enhanced': False,
                        'error': f"网络搜索失败: {search_result.get('error')}"
                    }
                
                # 4. 最终综合分析
                current_app.logger.info("语义预分析 Slow Path: 开始最终综合分析")
                final_prompt = f"""请结合以下的原始地址列表和网络搜索结果，为这个任务生成一个最准确的主题名称，并分析这些地理实体的空间尺度特点。

原始地址列表：
{chr(10).join([f"{i+1}. {addr}" for i, addr in enumerate(sample_addresses)])}

网络搜索结果：
{search_result.get('llm_output', '')}

请以JSON格式返回结果，包含以下字段：
{{
    "theme_name": "最终的任务主题名称",
    "spatial_scale": "实体空间尺度（如'村镇级'、'区县级'等）",
    "entity_type": "实体类型描述"
}}"""
                
                final_response = await call_llm_api(final_prompt)
                
                if final_response.get('error') or not final_response.get('content'):
                    current_app.logger.warning(
                        f"语义预分析 Slow Path: 最终分析失败: {final_response.get('error')} (回退Fast Path)"
                    )
                    # 如果最终分析失败，返回初步结果
                    return {
                        'theme_name': theme_name,
                        'search_needed': search_needed,
                        'search_query': search_query,
                        'enhanced': False,
                        'error': f"最终分析失败: {final_response.get('error')}"
                    }
                
                # 解析最终分析结果
                try:
                    final_content = final_response['content'].strip()
                    json_match = re.search(r'```json\s*([\s\S]+?)\s*```', final_content)
                    if json_match:
                        json_str = json_match.group(1)
                    else:
                        json_str = final_content
                    
                    final_analysis = json.loads(json_str)
                    current_app.logger.info(
                        f"语义预分析 Slow Path: 增强成功，最终主题='{final_analysis.get('theme_name', theme_name)}', 空间尺度='{final_analysis.get('spatial_scale')}', 实体类型='{final_analysis.get('entity_type')}'"
                    )
                    
                    return {
                        'theme_name': final_analysis.get('theme_name', theme_name),
                        'spatial_scale': final_analysis.get('spatial_scale'),
                        'entity_type': final_analysis.get('entity_type'),
                        'search_needed': search_needed,
                        'search_query': search_query,
                        'enhanced': True,
                        'error': None
                    }
                    
                except json.JSONDecodeError as e:
                    print(f"解析最终分析JSON失败: {e}")
                    print(f"原始响应: {final_content}")
                    current_app.logger.warning(f"语义预分析 Slow Path: 最终分析JSON解析失败: {str(e)} (回退Fast Path)")
                    # 返回初步分析结果作为fallback
                    return {
                        'theme_name': theme_name,
                        'search_needed': search_needed,
                        'search_query': search_query,
                        'enhanced': False,
                        'error': f"最终分析JSON解析失败: {str(e)}"
                    }
                    
            except Exception as e:
                print(f"网络搜索阶段出错: {str(e)}")
                current_app.logger.warning(f"语义预分析 Slow Path: 网络搜索阶段出错: {str(e)} (回退Fast Path)")
                # 返回初步分析结果作为fallback
                return {
                    'theme_name': theme_name,
                    'search_needed': search_needed,
                    'search_query': search_query,
                    'enhanced': False,
                    'error': f"网络搜索阶段出错: {str(e)}"
                }
        
        # 如果不需要搜索，直接返回初步分析结果
        current_app.logger.info("语义预分析 Slow Path: 未触发（无需联网搜索）")
        return {
            'theme_name': theme_name,
            'search_needed': search_needed,
            'search_query': search_query,
            'enhanced': False,
            'error': None
        }
        
    except Exception as e:
        print(f"批量语义分析出错: {str(e)}")
        traceback.print_exc()
        current_app.logger.error(f"批量语义分析出错: {str(e)}")
        return {
            'theme_name': '地理编码任务',
            'search_needed': False,
            'search_query': None,
            'error': f"批量语义分析失败: {str(e)}"
        }

def _smart_sample_addresses(addresses: list, max_size: int) -> list:
    """
    智能抽样地址列表
    
    :param addresses: 原始地址列表
    :param max_size: 最大抽样数量
    :return: 抽样后的地址列表
    """
    if len(addresses) <= max_size:
        return addresses
    
    # 简单的均匀抽样策略
    # 未来可以考虑更复杂的策略，如地域分布均衡抽样
    step = len(addresses) // max_size
    sampled = []
    
    for i in range(0, len(addresses), step):
        if len(sampled) >= max_size:
            break
        sampled.append(addresses[i])
    
    # 确保抽样数量正确
    if len(sampled) < max_size and len(addresses) > len(sampled):
        # 补充末尾的地址
        remaining_slots = max_size - len(sampled)
        start_idx = len(addresses) - remaining_slots
        for i in range(max(start_idx, len(sampled) * step), len(addresses)):
            if len(sampled) >= max_size:
                break
            if addresses[i] not in sampled:  # 避免重复
                sampled.append(addresses[i])
    
    return sampled[:max_size] 