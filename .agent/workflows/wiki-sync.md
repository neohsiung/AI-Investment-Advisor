---
description: 当源码变更时自动同步更新Wiki文档
---

# Wiki Documentation Sync Workflow

## 目的 (Purpose)

当源码有重大变更时，自动识别需要更新的Wiki文档并生成更新建议，确保文档与代码保持一致。

## 触发时机 (When to Run)

- ✅ 新增模块/服务后
- ✅ 重大功能完成后（如v3.6 Leverage Engine）
- ✅ API接口变更后
- ✅ 架构调整后
- ✅ 每个milestone完成时
- ✅ **Commit 前检查** (Pre-commit check)

## 执行步骤 (Steps)

### 1. 分析源码变更

识别变更的文件:
```bash
# 查看最近变更的Python文件 (过去7天)
find src/ -name "*.py" -mtime -7 -type f
```

记录变更类型:
- **新增**: 新的class/function
- **修改**: 现有class/function签名变更
- **删除**: 已移除的模块

### 2. 映射到相关Wiki文档

**映射规则表**:

| 源码目录 | 对应Wiki文档 |
|:---------|:-------------|
| `src/agents/` | `04_架構觀點-Architect_Views/代理架構-Agent-Architecture.md` |
| `src/services/` | `03_開發者指南-Developer_Guide/服務層開發指南-Service-Layer-Blueprints.md` |
| `src/infrastructure/` | `04_架構觀點-Architect_Views/底層通信協議-Agent-Mesh-Protocols.md` |
| `src/data/providers/` | `03_開發者指南-Developer_Guide/外部數據整合-External-Data-Integration.md` |
| `src/repositories/` | `03_開發者指南-Developer_Guide/數據層設計-Data-Layer-Design.md` |
| Broker services | `03_開發者指南-Developer_Guide/券商整合指南-Broker-Integration-Guide.md` |
| 新milestone功能 | `02_產品經理-Product_Managers/產品演進藍圖-Evolutionary-Roadmap.md` |

### 3. 检查不一致性

**检查项**:

- [ ] **模块引用**: Wiki中提到的class/function是否仍存在？
  ```bash
  # 查找Wiki中引用但不存在的类
  grep -r "class SomeClass" wiki/ --include="*.md"
  grep -r "SomeClass" src/ --include="*.py"
  ```

- [ ] **API签名**: 函数参数是否还匹配？
- [ ] **配置说明**: 环境变量/设定是否正确？
- [ ] **代码示例**: 示例代码是否还能运行？

### 4. README.md 检查 (Pre-commit)

**规则参照**: `.agent/rules/readme-standards.md`

- [ ] **版本纪录**: 是否包含最新变动？
- [ ] **双语同步**: 中英文内容是否一致？
- [ ] **覆盖率徽章**: 是否反映当前测试覆盖率 (75%)？
- [ ] **坏链检查**: 文档索引中的Wiki链接是否有效？

### 5. 生成更新建议

**输出格式**:

```markdown
## Wiki Update Recommendations

### 文件: wiki/03_開發者指南-Developer_Guide/服務層開發指南-Service-Layer-Blueprints.md

**变更原因**: src/services/analytics_service.py 新增 Leverage Engine

**建议更新**:
1. 添加版本纪录 (v3.6, 2026-02-15)
2. 新增章节: "Leverage Engine - 槓桿計算"
3. 补充代码示例:
   ```python
   analytics = AnalyticsService()
   net_equity = analytics.calculate_net_equity(positions)
   ```
4. 更新架构图（如需要）

**优先级**: P1 (缺漏信息)
```

### 5. 执行文档更新

根据建议，更新相应wiki文档:

**标准流程**:
1. 更新版本纪录（顶部表格）
2. 修改/新增相关章节
3. 确保双语并列（中文 + English）
4. 使用backticks引用代码元素
5. 添加文件链接（如适用）

**示例更新**:
```markdown
### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-15 | v3.6 | 新增 Leverage Engine 計算說明 | Neo |
| ... | ... | ... | ... |

## Leverage Engine (v3.6 新增)

**位置**: [`analytics_service.py`](file:///path/to/analytics_service.py)

**功能**: 精確計算淨權益與貸款金額...
```

### 6. 验证更新

- [ ] 所有代码引用使用backticks
- [ ] 文件链接可点击（VSCode测试）
- [ ] 版本纪录已更新
- [ ] 双语内容完整

## 优先级判断 (Prioritization)

### P0 - 立即修正 (错误信息)
- 引用不存在的模块/类
- 已废弃的API文档
- 错误的配置说明

### P1 - 应该补充 (缺漏信息)
- 新功能未记录（如v3.6 Leverage Engine）
- Milestone达成未更新（如75%覆盖率）
- 架构变更未反映

### P2 - 可选优化 (增强内容)
- 补充代码示例
- 优化架构图
- 改进翻译质量

## 自动化提示 (Automation Tips)

### 查找可能过时的Wiki引用
```bash
# 列出Wiki中引用的Python类
grep -roh 'class [A-Za-z_]*' wiki/ --include="*.md" | sort | uniq > wiki_classes.txt

# 列出src中实际存在的类
grep -roh '^class [A-Za-z_]*' src/ --include="*.py" | sort | uniq > src_classes.txt

# 比较差异
diff wiki_classes.txt src_classes.txt
```

### 检查代码示例是否能运行
```bash
# 提取Wiki中的Python代码块
# (需要手动验证)
grep -A 10 "```python" wiki/*.md
```

## 成功标准 (Success Criteria)

- ✅ 0 个不存在的模块/类别引用
- ✅ 100% 核心功能有对应文档
- ✅ 所有Wiki链接有效
- ✅ 新功能在1周内补充文档

## 参考 (References)

- [Wiki标准规范](../wiki/05_工程手冊-Engineering_Handbook/02_規範標準-Standards/文件規範-Wiki-Standard.md)
- [README标准规范](../.agent/rules/readme-standards.md)
- [文档框架定义](../wiki/05_工程手冊-Engineering_Handbook/02_規範標準-Standards/文件框架定義-Document-Frameworks.md)
