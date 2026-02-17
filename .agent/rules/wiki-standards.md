# Wiki Documentation Standards

## 强制要求 (Mandatory Requirements)

### 1. 版本纪录 (Version History)

**每个**Wiki文档顶部必须包含版本历史表格：

```markdown
### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| YYYY-MM-DD | vX.Y | 描述变更内容 | Author Name |
```

**示例**:
```markdown
### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-15 | v3.6 | 新增 Leverage Engine 計算說明 | Neo |
| 2026-02-14 | v3.5 | Initial Release | Neo |
```

### 2. 双语并列 (Bilingual Content)

**所有**Wiki文档必须包含**中文**和**英文**两个版本,格式：

```markdown
# 文档标题 (Document Title)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 中文内容开始

...

---

<a id="en"></a>

## 🇺🇸 English Content

...
```

**顺序**: 繁体中文在上，English在下

### 3. 代码引用规范 (Code References)

- **类名**: 使用backticks - `` `AnalyticsService` ``
- **函数名**: 使用backticks - `` `calculate_net_equity()` ``
- **文件路径**: 使用backticks - `` `src/services/analytics_service.py` ``
- **配置项**: 使用backticks - `` `POLYGON_API_KEY` ``
- **命令**: 使用backticks - `` `pytest --cov` ``

**错误示例** ❌:
```markdown
AnalyticsService 提供了 calculate_net_equity 功能
```

**正确示例** ✅:
```markdown
`AnalyticsService` 提供了 `calculate_net_equity()` 功能
```

### 4. 文件链接 (File Links)

使用markdown链接格式，路径为**绝对路径**：

```markdown
详见 [`analytics_service.py`](file:///absolute/path/to/analytics_service.py)
```

或使用相对链接到其他wiki文档：

```markdown
详见 [服務層開發指南](服務層開發指南-Service-Layer-Blueprints.md)
```

### 5. 更新触发 (Update Triggers)

以下情况**必须**更新相关Wiki文档：

- ✅ **新增模块/服务** → 更新对应架构/开发指南
- ✅ **API接口变更** → 更新服务层文档
- ✅ **新增配置项** → 更新环境设定文档
- ✅ **Milestone达成** → 更新产品演进蓝图
- ✅ **架构变更** → 更新架构观点文档

**更新时必须**:
1. 添加新的版本纪录行
2. 在相关章节说明变更
3. 保持双语同步

### 6. 命名规范 (Naming Convention)

Wiki文件命名格式：

```
{繁体中文}-{English}.md
```

**示例**:
- ✅ `產品演進藍圖-Evolutionary-Roadmap.md`
- ✅ `測試與外部服務整合-Testing-External-Services.md`
- ❌ `roadmap.md`
- ❌ `测试指南.md` (简体中文)

### 7. 文档结构 (Document Structure)

标准结构：

```markdown
### 版本紀錄 (Version History)
...

---

<a id="zh"></a>

## 🇹🇼 主题名称

### 章节1
内容...

### 章节2
内容...

## 🔗 双向链接 (Bidirectional Links)
- [相关文档1](...)
- [相关文档2](...)

---

<a id="en"></a>

## 🇺🇸 Topic Name

### Section 1
Content...
```

## 质量检查清单 (Quality Checklist)

在提交文档前检查:

- [ ] 顶部有版本纪录表格
- [ ] 中英文双语完整
- [ ] 所有代码元素使用backticks
- [ ] 文件链接格式正确
- [ ] 文件名符合命名规范
- [ ] 无拼写错误（尤其是英文部分）
- [ ] Markdown格式正确（标题层级、列表等）

## 违规示例与修正 (Common Violations)

### 示例1: 缺少版本纪录
❌ **错误**:
```markdown
# 服务层开发指南

## 概述
本文档说明...
```

✅ **正确**:
```markdown
### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-15 | v3.6 | Initial Release | Neo |

---

# 服务层开发指南
...
```

### 示例2: 代码未使用backticks
❌ **错误**:
```markdown
AnalyticsService的calculate_net_equity函数计算净权益
```

✅ **正确**:
```markdown
`AnalyticsService`的`calculate_net_equity()`函数计算净权益
```

### 示例3: 只有中文没有英文
❌ **错误**:
只有中文内容，无English section

✅ **正确**:
包含完整的中文和English两部分

## Git 同步規範 (Git Synchronization Standard)

**強制要求 (Mandatory)**: 當變更涉及 Wiki 內容時，必須在同一個任務週期內完成 Wiki Repo 的提交。

- **即時性**: 代碼變更與對應的文檔更新應同時提交，嚴禁「事後補檔」。
- **檢查機制**: 在執行最後的 Commit 操作前，Agent 必須主動檢查 `wiki/` 目錄的狀態。
- **雙 Repo 同步**: 確保主 Repo 的 `docs(wiki)` 提及與 Wiki Repo 的實際內容保持一致。

## 自动化检查 (Automated Checks)

### 检查是否有版本纪录
```bash
# 查找缺少版本纪录的wiki文件
grep -L "版本紀錄" wiki/**/*.md
```

### 检查是否双语
```bash
# 查找缺少English section的文件
grep -L "<a id=\"en\">" wiki/**/*.md
```

### 检查代码引用
```bash
# 查找可能未加backticks的类名 (需人工复核)
grep -n "Service " wiki/**/*.md | grep -v "`"
```

## 参考 (References)

- [文档框架定义](../wiki/05_工程手冊-Engineering_Handbook/02_規範標準-Standards/文件框架定義-Document-Frameworks.md)
- [Wiki标准规范](../wiki/05_工程手冊-Engineering_Handbook/02_規範標準-Standards/文件規範-Wiki-Standard.md)
