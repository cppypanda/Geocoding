# 地址查找工具中的 POI 搜索功能规格说明

本文档旨在作为地址查找工具中 POI (Point of Interest) 搜索功能的功能规格说明（FSD），并兼具标准操作流程（SOP）指南的功能。文档将详细描述该功能的用户交互、业务逻辑和预期行为。

## 1. 功能概述

POI（Point of Interest，兴趣点）搜索是地址查找工具的核心功能之一。它允许用户通过输入关键词，在集成的多个地图服务商（包括高德地图、百度地图和天地图）中查找相关的地理位置点。系统会将搜索到的结果以列表形式清晰地展示给用户，便于用户进行甄别和选择，以完成地址的精确定位。

## 2. 用户界面与交互流程

### 2.1. 界面元素
用户进行POI搜索主要会接触到以下界面元素：
- **搜索输入框**: 用于输入地点、名称、地址片段等搜索关键词。该输入框会自动填充“逐一校准”面板中当前待处理的地址，并智能移除地址中的通用后缀（如“小区”、“大厦”等），以提取核心关键词，提升搜索精度。
- **数据源选择器**: 一个下拉菜单，允许用户在不同的地图服务提供商（高德地图、百度地图、天地图）之间切换，以从不同来源获取数据。
- **搜索按钮**: 用于触发搜索操作。
- **结果展示表格**: 一个动态表格，用于展示从后端获取的POI搜索结果。表格标题旁会明确标注本次搜索结果所使用的地图服务商（例如：“地图搜索结果 - 高德地图”）。

### 2.2. 标准操作流程
1.  **输入与触发**: 用户确认“搜索输入框”中的默认关键词（或手动修改后），并从“数据源选择器”中选择一个地图服务商。通过点击“搜索按钮”或在输入框中按回车键来启动搜索。
2.  **请求发送**: 操作触发后，界面会向系统后端发送一个包含“关键词”和“数据源”信息的请求。在等待后端返回数据的过程中，界面会显示一个加载动画，以提示用户系统正在处理。
3.  **结果处理与展示**: 系统后端返回POI列表后，会**自动进行一次辅助决策分析**。随后，界面会动态地将这些结果填充到“结果展示表格”中。表格的每一行代表一个POI，并清晰地展示其**名称**、**地址**、**行政区划**以及系统自动计算的**置信度分数**。如果辅助决策分析成功推荐了一个最佳匹配项，其对应的“选定”按钮将自动处于选中状态。
4.  **结果选定**: 每一条结果旁边都有一个“选定”按钮。用户可以接受系统的此项预选结果，也可以手动点击其他POI的“选定”按钮来覆盖此推荐。确认选择后，系统会将这个选定的POI的完整信息（名称、地址、经纬度等）应用到当前正在处理的地址记录上，从而完成对该地址的校准工作。

### 2.3. 单点POI结果缓存
为了提升批量地址校准时的操作效率，系统具备针对单个地址的POI搜索结果缓存机制。
- **过程缓存**: 在“逐一校准”模式下，当用户为某一个地址（例如第N条）执行了POI搜索后，该次搜索返回的完整POI列表以及用户的最终“选定”状态，都会被临时缓存下来。
- **无缝回显**: 如果用户在校准后续地址（例如第N+1条）的过程中，又切回到之前的地址（第N条），系统会自动从缓存中加载并展示当时的POI结果列表和“选定”状态，无需重新发起搜索，从而保证了操作的流畅性和连续性。

## 3. 后端处理逻辑

### 3.1. 统一的API入口
系统后端提供一个统一的API接口来处理所有来源的POI搜索请求。这种设计简化了前后端的通信，使得前端无需关心不同地图服务商的接口差异。

### 3.2. 请求分发与处理
1.  **请求接收**: 后端API入口接收到前端发来的请求后，会首先解析出其中的“关键词”和“数据源”参数。
2.  **动态分发**: 系统会根据“数据源”参数（例如 `amap`, `baidu`, `tianditu`），智能地将请求分发给内部相应的服务模块进行处理。每个服务模块都专门负责与一个特定的第三方地图API进行通信。
3.  **外部API通信**: 被选中的服务模块会使用系统管理的有效API密钥，构造符合该地图服务商规范的请求，并向其发送。

### 3.3. 数据标准化与增强
从第三方地图API获取到原始数据后，服务模块会立即进行一系列的标准化和数据增强处理，以确保返回给前端的数据是统一、干净且包含附加价值的。
1.  **数据解析**: 此步骤是标准化的核心。由于不同地图服务商返回的数据结构各不相同（详情见附录A），本模块会根据数据源，精确地从复杂的原始响应中提取出名称、地址、省市区、经纬度等核心字段，并映射到系统内部的统一数据模型上。
2.  **坐标系转换**: 为了保证整个系统内部坐标系的统一，所有从第三方获取的坐标（如高德的GCJ-02坐标系）都会被转换成国际标准的WGS-84坐标系。转换前后的坐标都会被保留。
3.  **置信度计算**: 系统会运行一个内部算法，通过比较原始关键词与返回结果的名称、地址等信息，为每一条POI计算一个“置信度分数”。这个分数是衡量结果相关性的关键指标。
4.  **统一格式化**: 最后，所有处理好的数据会被封装成一个标准化的、统一的JSON格式返回给前端界面。

## 4. 辅助决策功能

为了提升用户在处理复杂或模糊地址时的校准效率，系统提供了两种核心的辅助决策功能：自动置信度评估和基于大语言模型的智能选点。

### 4.1. 自动置信度评估
置信度评估并非一个独立的功能，而是无缝集成在每一次POI搜索流程中的核心环节。系统在返回任何搜索结果之前，都会自动为每一条POI计算置信度。这使得用户在浏览结果列表时，能够通过比较分数，快速地判断出哪些是高概率的匹配项，从而极大地提高了人工筛选的效率。关于该算法的详细技术规格，请参阅《置信度算法规格书 (SOP_Confidence_Algorithm.md)》。

### 4.2. 大语言模型智能选点
该功能是系统提升地址校准自动化水平的关键。它已深度集成到POI搜索流程中，作为一项自动触发的增强服务。
- **自动触发**: 用户点击“搜索”按钮后，一旦后端获取并标准化POI列表，智能选点流程便会自动启动。尤其是在所有候选POI的置信度均未达到高可信阈值（如90%）时，该功能将发挥核心作用。
- **后端处理**: 系统会将用户输入的“原始地址”以及当前POI结果列表一并发送至后端。
- **LLM分析**: 后端会调用一个强大的大语言模型（LLM），让它从语义层面理解“原始地址”与POI候选列表之间的内在联系，综合上下文、别名、地理常识进行深度分析。
- **返回建议**: LLM分析完成后，会返回它认为最匹配的那个POI以及选择该POI的理由。系统随后会在前端界面上将此推荐结果的“选定”按钮置为选中状态，并展示推荐理由，辅助用户做出最终决策。（注：未来的版本规划中，原有的手动“智能选点”按钮将被移除，完全依赖此自动化流程。）

## 5. 数据流总结

1.  **用户** 在前端界面输入关键词，选择数据源（如高德），并点击搜索。
2.  **前端脚本** 将关键词和数据源（`source`）打包，发送一个 `POST` 请求到后端的统一POI搜索接口 (`/geocode/poi_search`)。
3.  **后端路由** 接收请求，并根据 `source` 参数，将任务分发给对应的 **地图服务模块**（如高德服务模块）。
4.  **地图服务模块** 负责调用 **第三方地图API** (高德、百度等)，并附上有效的API密钥。
5.  第三方地图API返回原始POI数据。
6.  **地图服务模块** 对返回的数据进行 **标准化处理**（坐标转换、计算置信度等），并将其格式化为统一的JSON结构。
7.  **（自动辅助决策）** 后端服务在拿到标准化的POI列表后，会自动调用 **大语言模型（LLM）进行智能选点分析**，尝试找出最佳匹配项。
8.  **后端** 将处理好的、且可能包含LLM推荐信息的JSON数据返回给前端。
9.  **前端脚本** 解析JSON数据，并在页面的结果表格中清晰地展示出来。如果数据中包含LLM的推荐结果，则相应地**将其“选定”按钮置为选中状态**。
10. **用户** 在表格中选择一个最合适的POI，前端脚本将该POI的详细信息应用于当前正在处理的地址记录，完成校准。 

## 附录A：各地图请求与返回参数



### A.1 高德地图 · 关键字搜索

- **API 服务地址**: `https://restapi.amap.com/v5/place/text?parameters`
- **请求方式**: GET
- **请求参数**
    - **key**: 高德 Key。用户需在高德地图官网申请 Web 服务 API Key。必填；默认无。
    - **keywords**: 地点关键字。仅支持一个关键字，文本总长度≤80字符。必填（与 `types` 二选一）；默认无。
    - **types**: 指定地点类型，可传多个 poi typecode，使用 `|` 分隔；排序由高德综合权重决定。可选（与 `keywords` 二选一）；示例：120000（商务住宅）、150000（交通设施服务）。
    - **region**: 搜索区划。提升指定区域内召回权重；如需严格限制区域，请配合 `city_limit`。支持 `citycode`、`adcode`、`cityname`（仅支持城市级别且中文，如“北京市”）。可选；默认全国。
    - **city_limit**: 指定城市数据召回限制。`true/false`；为 `true` 时仅召回 `region` 对应区域。可选；默认 `false`。
    - **show_fields**: 返回结果控制。多个字段用逗号分隔；未设置时仅返回基础信息类字段。可选；默认空。
    - **page_size**: 当前分页条数，取值 1-25。可选；默认 10。
    - **page_num**: 请求第几页。可选；默认 1。
    - **sig**: 数字签名。可选。
    - **output**: 返回格式，仅支持 `json`。可选；默认 `json`。
    - **callback**: 回调函数名，仅在 `output=json` 时有效。可选；默认无。
- **请求示例**
```text
https://restapi.amap.com/v5/place/text?keywords=北京大学&types=141201&region=北京市&key=<您的key>
```
- **返回参数（顶层）**
    - **status**: string。本次访问状态，成功为 `1`，失败为 `0`。
    - **info**: string。状态说明，成功为 `ok`，失败为错误原因。
    - **infocode**: string。状态码，`10000` 代表正确。
    - **count**: string。单次请求返回的实际 POI 个数。
    - **pois**: array。POI 集合。
- **POI 字段（基础信息）**
    - **name**: string，POI 名称
    - **id**: string，POI 唯一标识
    - **location**: string，POI 经纬度
    - **type**: string，POI 所属类型
    - **typecode**: string，POI 分类编码
    - **pname**: string，所属省份
    - **cityname**: string，所属城市
    - **adname**: string，所属区县
    - **address**: string，详细地址
    - **pcode**: string，省份编码
    - **adcode**: string，区域编码
    - **citycode**: string，城市编码
- **可选扩展字段（需通过 `show_fields` 指定）**
    - **children**: 子 POI 信息
        - id, name, location, address, subtype, typecode, sname, subtype（再次确认）
    - **business**: 商业信息
        - business_area, opentime_today, opentime_week, tel, tag, rating, cost, parking_type, alias, keytag, rectag
    - **indoor**: 室内相关
        - indoor_map（1/0）, cpid, floor, truefloor
    - **navi**: 导航位置
        - navi_poiid, entr_location, exit_location, gridcode
    - **photos**: 图片信息
        - title, url


### A.2 天地图 · 行政区划区域搜索服务（queryType=12）

- **API 服务地址**: `http://api.tianditu.gov.cn/v2/search`
- **请求方式**: GET（通过 `postStr` 传 JSON 参数，`tk` 为密钥）
- **输入参数**
    - **keyWord**: 搜索关键字。String；必填。
    - **specify**: 指定行政区国标码或名称（按行政区划编码表，9 位，如北京 `156110000` 或“北京”）。String；必填。
    - **queryType**: 服务查询类型。String；必填；取值 `12` 表示行政区划区域搜索。
    - **start**: 结果起始位（分页/缓存）。String；必填；0-300。
    - **count**: 返回条数（分页/缓存）。String；必填；1-300。
    - **dataTypes**: 数据分类（编码或名称，多值用英文逗号分隔）。String；可选。
    - **show**: 返回 POI 信息类别。取值 `1` 基本信息；`2` 详细信息。可选。
- **请求示例**
```text
http://api.tianditu.gov.cn/v2/search?postStr={"keyWord":"商厦","queryType":12,"start":0,"count":10,"specify":"156110108"}&type=query&tk=<您的密钥>
```
- **返回参数（通用）**
    - **resultType**: Int。返回类型 1-5：1 普通POI；2 统计；3 行政区；4 建议词；5 线路。
    - **count**: Int。返回总条数。
    - **keyword**: String。搜索关键词。
    - **status**: Json 数组。结果提示信息。
        - **infocode**: Int。服务状态码。
        - **cndesc**: String。中文描述。
- **resultType=1（POI 列表）**
    - **pois**: Json 数组
        - name(String) 必返；phone(String)；address(String)
        - lonlat(String) 必返，坐标 `x,y`
        - poiType(Int) 必返：101 POI 数据；102 公交站点
        - eaddress(String)；ename(String)
        - hotPointID(String) 必返
        - province/provinceCode/city/cityCode/county/countyCode(String)
        - source(String) 必返；typeCode(String)；typeName(String)
        - stationData(Json 数组，poiType=102 时返回)
            - lineName(String) 必返；uuid(String) 必返；stationUuid(String) 必返
- **resultType=2（统计）**
    - **statistics**: Json 数组
          - adminCode(Int) 必返；level(Int) 必返（1-18）
- **resultType=5（线路）**
    - **lineData**: Json 数组
        - stationNum(String) 必返；poiType(String，恒为“103”) 必返
        - name(String) 必返；uuid(String) 必返


### A.3 百度地图 · 地点检索 3.0（行政区划区域检索）

- **API 服务地址**: `https://api.map.baidu.com/place/v3/region`
- **请求方式**: GET
- **请求参数**
    - **query**: 检索关键字（如“天安门”、“美食”）。必填。
    - **region**: 行政区划（支持到区县）。提升区域内召回权重；如需严格限制，请配合 `region_limit`。可输入行政区名或 `citycode`。必填。
    - **ak**: 开发者访问密钥。必填。
    - **region_limit**: 区域限制，`true/false`；为 `true` 时仅召回 `region` 对应区域。可选。
    - **is_light_version**: 轻量模式。`true` 更快、排序简单；`false`（默认）更贴近百度地图推荐顺序。可选。
    - **type**: 对 `query` 结果进行二次筛选；建议与 `query` 同一大类（如 `query=美食`，`type=火锅`）。`query` 与 `type` 支持只填一项。可选。
    - **center**: 传入 POI 坐标（`lat,lng`），辅助按距离排序；需配合排序字段与 `coord_type` 使用。可选。
    - **scope**: 结果详细程度。`1` 或空：基本信息；`2`：返回详细信息。可选。
    - **coord_type**: 传入坐标类型。`1`=wgs84ll；`2`=gcj02ll；`3`=bd09ll（默认）；`4`=bd09mc。可选。
    - **filter**: 排序条件：`industry_type`（hotel/cater/life）、`sort_name`（default/price/overall_rating/distance[需配合 center]）、`sort_rule`（0 高→低，1 低→高）。可选。
    - **extensions_adcode**: 是否召回国标行政区划编码。`true/false`。可选。
    - **address_result**: `query` 为结构化地址时的返回类型；不传默认召回门址数据；当 `address_result=false` 时召回相应的 POI 数据。可选。
    - **photo_show**: 是否输出图片信息。`true/false`；默认 `false`。可选（需商用授权）。
    - **from_language**: `query` 语言类型，默认中文；可设 `auto`。可选。
    - **language**: 多语言检索（高级付费），如 `en`、`fr`。可选。
    - **page_num**: 分页页码，默认 0（第一页）。可选。
    - **page_size**: 单次召回 POI 数量，默认 10，最大 20。可选。
    - **ret_coordtype**: 返回坐标类型（如 `gcj02ll`）。可选。
    - **output**: 输出格式，仅 `json`。可选。
- **返回参数（顶层）**
    - **status**: int。成功返回 `0`，失败为其他数字。
    - **message**: string。状态说明；成功为 `ok`。
    - **total**: int。召回 POI 数量（仅当请求设置了 `page_num` 时出现，且单次最多 150）。
    - **result_type**: string。结果类型：`region_type`/`address_type`/`poi_type`/`city_type`。
    - **query_type**: string。搜索类型：精搜 `precise` / 泛搜 `general`。
    - **results**: array。结果列表。
- **结果项（poi_type 时）**
    - **uid**: string，POI 唯一标识
    - **name**: string，POI 名称（单次最多返回 10 条）
    - **location**: object，经纬度坐标（lat、lng）
    - **province/city/area**: string，所属省/市/区县
    - **town**: string，所属乡镇街道；**town_code**: int，乡镇街道编码
    - **adcode**: int，区域代码
    - **address**: string，地址
    - **status**: string，营业状态（空/推算位置/暂停营业/可能已关闭/已关闭 等，部分为商用能力）
    - **telephone**: string，电话
    - **street_id**: string，街景图 id
    - **detail**: string，是否有详情页（1/0）
    - **detail_info**: object，详细信息
        - classified_poi_tag, new_alias, type（hotel/cater/life 等，与 `filter` 搭配）
        - detail_url, shop_hours, price, label, overall_rating, image_num, comment_num
        - navi_location（导航引导点），brand，indoor_floor，ranking，parent_id
        - photos（array，图片链接；商用能力），best_time，sug_time，description
    - **children**: 子点
        - uid, show_name, name, classified_poi_tag, location, address
     - count(Int) 必返：本次统计 POI 总数量
        - adminCount(Int) 必返：行政区数量
        - priorityCitys(Json 数组) 必返：推荐行政区名称
        - name(String) 必返；count(Int) 必返；lonlat(String) 必返（`x,y`）
        - ename(String) 必返；adminCode(Int) 必返（9 位国标码）
        - allAdmins(Json 数组) 必返
            - name(String) 必返；count(Int) 必返；lonlat(String) 必返（`x,y`）
            - adminCode(String) 必返；ename(String) 必返；isleaf(boolean) 必返（有下级为 false）
- **resultType=3（行政区）**
    - **area**: Json 数组
        - name(String) 必返；bound(String，“minx,miny,maxx,maxy”)；lonlat(String) 必返
 
