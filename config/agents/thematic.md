---
# The Markdown body of this file (after the closing ---) is the agent's
# system prompt. It is intentionally EMPTY: this agent resolves its prompt
# from workspace/<workspace>/IDENTITY.md + SOUL.md, and duplicating that text
# here would create a second source that drifts. Add a body ONLY to override
# the workspace prompt.
#
# Resolution order (BaseAgent._load_prompt): stored override in
# user_custom_prompts > this body > workspace files > legacy prompts/*.txt
#
# 本檔結尾分隔線之後的 Markdown 本文即為系統提示詞，此處刻意留空：
# 該代理從 workspace/<workspace>/IDENTITY.md + SOUL.md 取得提示詞。
# 只有要覆寫 workspace 提示詞時才填寫本文。
id: thematic
display_name: Thematic
impl: thematic
default_tier: fast
description: Thematic and narrative positioning.
enabled: true
workspace: portfolio-manager
---
