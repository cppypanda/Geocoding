### 地址查找工具（三卡布局）功能规格与SOP（最终版草案）

本文档定义地址查找工具的新版“三卡布局”信息架构、交互与接口契约，用于指导前后端改造与测试。确认后据此实现。

---

## 一、整体信息架构

- 左侧（约 60% 宽）：POI 搜索卡片
  - 搜索输入、数据源选择（高德/百度/天地图）、搜索按钮
  - 结果表格（列：序号、名称、地址、所属区域、置信度[占位/可选]、操作）
  - 搜索栏下新增主按钮：智能选择（见第三章）
  - 结果地图与高亮交互保持现状（按需微调）

- 右侧（约 40% 宽）：上下两张卡片
  1) 网络信息获取卡片
     - 按钮：获取网络信息（消耗积分提示）
     - 结果：紧凑列表，仅呈现“原文句子”，去除“摘录1/2…”编号与来源；不再显示来源
  2) 关键词建议卡片
     - 按钮：生成关键词建议（必要时自动先获取网络信息）
     - 表格三列：关键词 | 建议理由及与原地址关系 | 操作（使用此关键词搜索POI）

- 响应式：在中小屏下右侧两卡片垂直堆叠到左侧之下；地图高度与表格区采用可滚动容器，避免溢出。

---

## 二、状态与数据流（前端）

- 状态管理主体：`WebIntelligenceManager`（现有 `static/js/modules/web-intelligence.js`）
  - `currentAddress: string|null`
  - `dossier: object|null`（Step1 结果）
  - `poiCandidates: array`（来自左侧 POI 搜索结果）
  - `validationResult: object|null`（Step2 结果）
  - `keywordSuggestions: array`（Step3 结果）

- 暴露方法（新增/强化）：
  - `setCurrentAddress(address)`：设置并在地址变更时重置相关状态
  - `setPoiCandidates(candidates)`：由 POI 搜索完成后调用
  - `hasDossier(): boolean`：是否已有网络信息
  - `ensureDossier(): Promise<void>`：若无则自动执行 Step1
  - `validateCandidatesOrAutoSelect(): Promise<ValidationOrSelectResult>`：有 dossier → 调 Step2；无 dossier → 调 `/auto_select_point`
  - `suggestKeywordsWithAutoFetch(): Promise<KeywordSuggestion[]>`：无 dossier 时先执行 Step1 再 Step3
  - `useKeywordForSearch(keyword)`：将关键词回填左侧搜索框并触发搜索

- 事件绑定：
  - 左侧 POI 搜索完成后：调用 `setPoiCandidates(results)` 同步给智能模块
  - 右侧按钮：
    - 获取网络信息 → `executeStep1`
    - 生成关键词建议 → `suggestKeywordsWithAutoFetch`
  - 左侧“智能选择”主按钮 → `validateCandidatesOrAutoSelect`

---

## 三、关键交互与分支策略

- 一键“智能选择”（左侧搜索栏下）
  - 前置：需有 POI 候选（否则提示先搜索）
  - 分支：
    - 若 `hasDossier() === true`：调用 Step2 接口 `/geocode/web_intelligence/validate_candidates`，用网络情报进行验证；返回匹配结果与`match_confidence`
    - 若 `hasDossier() === false`：调用 `/geocode/auto_select_point`（或直接采用混合点选第一阶段产出的置信度规则《SOP_Confidence_Algorithm.md》），进行无背景智能选点
  - 结果反馈：
    - 若有匹配：高亮推荐行（POI 表格），在“置信度”列显示置信度（Step2 的 `match_confidence` 或混合点选第一阶段计算的置信度，百分比）；弹出 toast 成功提示
    - 若无匹配：提示“可生成关键词建议”，并允许直接跳转到右侧关键词卡片

- 关键词建议卡片按钮
  - 若无 dossier：先执行 Step1，再执行 Step3
  - 渲染为表格：关键词 | 建议理由及与原地址关系 | 操作（“使用此关键词搜索” → 回填左侧并自动搜索）

- 网络信息获取卡片
  - 仅显示去重/聚合后的原文句子列表（不展示来源）
  - 成功后应刷新“前置条件提示”（使“智能选择”走 Step2）

---

## 四、后端接口契约（复用现有，必要时扩展）

- `POST /geocode/poi_search`
  - 入参：`{ keyword: string, source: 'amap'|'baidu'|'tianditu' }`
  - 出参：`{ success: boolean, results: Array<PoiItem> }`

- `POST /geocode/web_intelligence/search_collate`（Step1）
  - 入参：`{ original_address: string }`
  - 出参：`{ success: boolean, dossier: { collated_excerpts: Array<{ excerpt: string, sources: string[] }> , ... } }`

- `POST /geocode/web_intelligence/validate_candidates`（Step2）
  - 入参：`{ dossier: object, poi_candidates: PoiItem[] }`
  - 出参：`{ success: true, has_match: boolean, best_match_index?: number, selected_poi?: PoiItem, match_confidence?: number, validation_reason?: string, mismatch_reasons?: string[] }`
  - 可选增强（中期）：返回 per-candidate 评分数组 `scores: number[]` 以支持全表显示置信度

- `POST /geocode/web_intelligence/suggest_keywords`（Step3）
  - 入参：`{ original_address: string, dossier: object, mismatch_reasons?: string[] }`
  - 出参：`{ success: true, keyword_suggestions: Array<{ keyword: string, reason: string, search_strategy: string }> }`

- `POST /geocode/auto_select_point`（无背景智能选点）
  - 入参：`{ original_address: string, pois: PoiItem[], source_context?: string }`
  - 出参：`{ success: boolean, result?: { index: number } }`

---

## 五、UI 文案与提示

- 按钮与提示（建议示例）
  - 左侧：
    - “搜索”
    - “智能选择”（有背景情报时将使用情报增强）
  - 右上：
    - “获取网络信息” 小字：消耗积分
  - 右下：
    - “生成关键词建议” 小字：必要时将自动获取网络信息
  - Toast/提示：
    - 成功获取信息/生成建议/找到匹配POI等

- 置信度列说明
  - 先期：仅在被推荐行显示“置信度”（Step2 的 `match_confidence` 或混合点选第一阶段置信度）；其他行为空
  - 中期：如开放 per-candidate 分数，则全表显示并允许排序

---

## 六、样式与响应式

- 左 60% / 右 40% 基于 Bootstrap Grid（如 `col-lg-8` / `col-lg-4`）
- 右侧两卡片上下堆叠；中小屏下整体改为纵向堆叠
- 结果区与地图容器使用固定高度 + 内部滚动，避免页面抖动

---

## 七、兼容与迁移

- 移除 Tab 切换的依赖，将“智能地址情报”功能以两卡片承载
- 保持现有接口路径与数据结构，前端改造以最小侵入为原则
- 文档侧保留“三步骤”说明，但允许用户按需分离触发

---

## 八、实施阶段划分与验收要点

- 阶段一（必做）
  - 完成三卡布局与交互改造
  - 网络信息卡片的紧凑展示（去编号/来源可折叠）
  - 关键词建议表格化与“使用关键词搜索”联动
  - 左侧“符合度判断/智能选点”统一按钮与分支逻辑
  - 置信度列占位与推荐行高亮、百分比显示

- 阶段二（可选增强）
  - Step2 返回每候选评分数组，前端全表展示与排序
  - dossier 缓存（前端内存 + 后端短期缓存）与积分提示完善

- 验收要点
  - 在不手动切换 Tab 的情况下：搜索 → 一键判断/智能选点 → 若未匹配 → 一键生成关键词 → 关键词回填搜索，形成顺畅闭环
  - 中小屏与大屏显示良好，长内容不溢出，操作有明显反馈

---

## 九、术语与数据结构（摘录）

- PoiItem：与现有 `/geocode/poi_search` 返回结构保持一致
- Dossier：`{ original_address, collated_excerpts: [{ excerpt, sources[] }], ... }`
- ValidationOrSelectResult：兼容 Step2 与 `/auto_select_point` 的结果封装

---

最后更新：待确认


