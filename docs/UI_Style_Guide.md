# UI 样式指南

本文件定义了 GeoCoUI 应用的视觉风格、设计原则和组件美学。它是所有 UI 样式设计的唯一真实来源，旨在确保一致和高质量的用户体验。

## 1. 色彩规范 (Color Palette)

- **主色 (Primary Color)**: `#4A90E2` (用于主按钮、链接和激活状态)
- **辅助色 (Secondary Color)**: `#F5A623` (用于高亮、警告和次要操作)
- **背景色 (Background Color)**: `#F8F9FA` (应用主背景)
- **面板/卡片背景色 (Panel/Card Background)**: `#FFFFFF`
- **文本颜色 (Text Color)**: `#333333` (默认文本)
- **次要文本/柔和色 (Subtle Text/Muted Color)**: `#6c757d`
- **成功色 (Success Color)**: `#28a745`
- **错误色 (Error Color)**: `#dc3545`
- **边框颜色 (Border Color)**: `#DEE2E6`

## 2. 字体排版 (Typography)

- **主字体 (Primary Font Family)**: `"Microsoft YaHei UI", "Segoe UI", Tahoma, Geneva, Verdana, sans-serif`
- **等宽/代码字体 (Monospace/Code Font Family)**: `Consolas, "Courier New", monospace`

### 字号与字重 (Font Sizes & Weights)
- **H1 标题**: `28px`, `600`
- **H2 标题 (区域标题)**: `20px`, `600`
- **H3 标题**: `16px`, `600`
- **正文文本**: `14px`, `400`
- **小号文本/标签**: `12px`, `400`

### 行高 (Line Height)
- **默认行高**: `1.6`

## 3. 间距与布局 (Spacing & Layout)

- **基础单位**: `8px`
- **内边距 (小)**: `4px` (`0.5 * 基础单位`)
- **内边距 (标准)**: `8px` (`1 * 基础单位`)
- **内边距 (中)**: `16px` (`2 * 基础单位`)
- **内边距 (大)**: `24px` (`3 * 基础单位`)
- **布局间隙 (Layout Gutter)**: `16px`

## 4. 组件 (Components)

### 按钮 (Buttons)
- **边框圆角 (Border Radius)**: `4px`
- **内边距 (Padding)**: `8px 16px`
- **主按钮样式**: `background-color: var(--primary-color); color: white;`
- **悬停效果 (Hover Effect)**: `filter: brightness(95%);`
- **禁用状态 (Disabled State)**: `opacity: 0.65; cursor: not-allowed;`

### 输入框与文本域 (Input Fields & Text Areas)
- **边框 (Border)**: `1px solid var(--border-color)`
- **边框圆角 (Border Radius)**: `4px`
- **内边距 (Padding)**: `8px 12px`
- **焦点阴影 (Focus Shadow)**: `0 0 0 0.2rem rgba(74, 144, 226, 0.25)`

### 面板/卡片 (Panels / Cards)
- **边框 (Border)**: `1px solid var(--border-color)`
- **边框圆角 (Border Radius)**: `4px`
- **阴影 (Shadow)**: `0 1px 3px rgba(0,0,0,0.05)`

## 5. 图标 (Iconography)

- **图标库 (Library)**: Font Awesome (如果已集成)
- **使用原则 (Usage)**: 图标应谨慎、一致地使用以增强理解，而非纯粹为了装饰。 