"""
Channel Tone Adapter — Cross-Channel Response Post-Processor.
通道語氣適配器 — 跨通道回覆後處理器。

Adapts agent responses to match channel-specific constraints and formatting:
  - Telegram: Markdown supported, 2000 char limit, emoji-friendly
  - LINE: Plain text only, 500 char limit, emoji-friendly
  - Web: Full Markdown, 5000 char limit, formal tone

遵循規範:
  - 規範一 (Clean Architecture): 純函式，無外部依賴
  - 規範四 (模組化設計): 可獨立單元測試
  - 規範十五 (AI-Support First): Channel-aware output formatting
"""

import re
import logging
from dataclasses import dataclass
from typing import Dict

logger = logging.getLogger(__name__)


@dataclass
class ToneConfig:
    """Channel-specific formatting configuration."""
    max_length: int = 2000         # Character limit
    use_markdown: bool = True      # Whether channel supports Markdown
    use_emoji: bool = True         # Whether to keep emoji
    table_format: str = "markdown" # "markdown" | "text" | "none"
    truncation_suffix: str = "…\n\n（訊息過長，請在 Dashboard 查看完整內容）"


# ── Channel Configurations ────────────────────────────────

CHANNEL_TONES: Dict[str, ToneConfig] = {
    "telegram": ToneConfig(
        max_length=2000,
        use_markdown=True,
        use_emoji=True,
        table_format="markdown",
    ),
    "line": ToneConfig(
        max_length=500,
        use_markdown=False,
        use_emoji=True,
        table_format="text",
        truncation_suffix="…\n（更多內容請至 Dashboard 查看）",
    ),
    "web": ToneConfig(
        max_length=5000,
        use_markdown=True,
        use_emoji=False,
        table_format="markdown",
    ),
}

DEFAULT_TONE = ToneConfig()


class ChannelToneAdapter:
    """
    Post-processes agent responses for target channel formatting.
    對 Agent 回覆進行通道格式後處理。

    Usage:
        adapter = ChannelToneAdapter()
        formatted = adapter.adapt("**Bold** text with 📊 table", "line")
    """

    def __init__(self, custom_tones: Dict[str, ToneConfig] = None):
        self._tones = custom_tones or CHANNEL_TONES

    def adapt(self, response: str, channel_type: str) -> str:
        """
        Adapt agent response for the target channel.
        依據目標通道調整 Agent 回覆。

        Processing order:
        1. Strip Markdown if not supported
        2. Convert tables if needed
        3. Remove emoji if not wanted
        4. Truncate to max_length
        """
        if not response:
            return response

        config = self._tones.get(channel_type, DEFAULT_TONE)

        result = response

        # 1. Markdown handling
        if not config.use_markdown:
            result = self._strip_markdown(result)

        # 2. Table conversion
        if config.table_format == "text":
            result = self._convert_tables_to_text(result)
        elif config.table_format == "none":
            result = self._remove_tables(result)

        # 3. Emoji handling
        if not config.use_emoji:
            result = self._remove_emoji(result)

        # 4. Truncation
        if len(result) > config.max_length:
            result = self._truncate(result, config.max_length, config.truncation_suffix)

        return result

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """
        Remove Markdown formatting, preserving readable text.
        移除 Markdown 格式，保留可讀文字。
        """
        # Bold: **text** or __text__
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)

        # Italic: *text* or _text_
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'\1', text)

        # Strikethrough: ~~text~~
        text = re.sub(r'~~(.+?)~~', r'\1', text)

        # Inline code: `text`
        text = re.sub(r'`(.+?)`', r'\1', text)

        # Code blocks: ```...```
        text = re.sub(r'```[\s\S]*?```', '', text)

        # Headers: # Header → Header
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

        # Images: ![alt](url) → [alt]
        text = re.sub(r'!\[(.+?)\]\(.+?\)', r'[\1]', text)

        # Links: [text](url) → text
        text = re.sub(r'(?<!!)\[(.+?)\]\(.+?\)', r'\1', text)

        # Horizontal rules
        text = re.sub(r'^[-*_]{3,}\s*$', '---', text, flags=re.MULTILINE)

        # Lists: keep but normalize
        text = re.sub(r'^(\s*)[*+-]\s', r'\1• ', text, flags=re.MULTILINE)

        return text.strip()

    @staticmethod
    def _convert_tables_to_text(text: str) -> str:
        """
        Convert Markdown tables to aligned plain text.
        將 Markdown 表格轉為對齊的純文字。
        """
        lines = text.split('\n')
        result = []
        in_table = False
        table_rows = []

        for line in lines:
            stripped = line.strip()
            if '|' in stripped and stripped.startswith('|'):
                # Table separator row (e.g., |---|---|)
                if re.match(r'^\|[\s\-:]+\|', stripped):
                    in_table = True
                    continue
                # Table data row
                cells = [c.strip() for c in stripped.split('|')[1:-1]]
                table_rows.append(cells)
                in_table = True
            else:
                if in_table and table_rows:
                    # Flush table as aligned text
                    result.extend(_render_text_table(table_rows))
                    table_rows = []
                    in_table = False
                result.append(line)

        # Flush remaining table
        if table_rows:
            result.extend(_render_text_table(table_rows))

        return '\n'.join(result)

    @staticmethod
    def _remove_tables(text: str) -> str:
        """Remove entire Markdown tables from text."""
        lines = text.split('\n')
        result = []
        skip = False
        for line in lines:
            stripped = line.strip()
            if '|' in stripped and stripped.startswith('|'):
                skip = True
                continue
            else:
                skip = False
            
            result.append(line)
        return '\n'.join(result)

    @staticmethod
    def _remove_emoji(text: str) -> str:
        """
        Remove emoji characters from text.
        從文字中移除 Emoji 字元。
        """
        # Each range is a separate compile call to avoid overly broad character classes
        # that could be flagged by static analysis (CodeQL: overly permissive regex range).
        _emoji_sub = re.compile(
            r"[\U0001F600-\U0001F64F"   # emoticons
            r"\U0001F300-\U0001F5FF"    # symbols & pictographs
            r"\U0001F680-\U0001F6FF"    # transport & map symbols
            r"\U0001F900-\U0001F9FF"    # supplemental symbols & pictographs
            r"\U0001FA00-\U0001FA6F"    # chess symbols
            r"\U0001FA70-\U0001FAFF"    # symbols & pictographs extended-B
            r"\U00002702-\U000027B0"    # dingbats
            r"\U0000FE00-\U0000FE0F"    # variation selectors
            r"\U0000200D"               # zero width joiner
            r"\U00002600-\U000026FF"    # miscellaneous symbols
            r"]+",
            flags=re.UNICODE,
        )
        emoji_pattern = _emoji_sub
        return emoji_pattern.sub("", text).strip()

    @staticmethod
    def _truncate(text: str, max_length: int, suffix: str) -> str:
        """
        Truncate text to max_length, adding suffix.
        截斷文字至 max_length，加上後綴。
        """
        if len(text) <= max_length:
            return text

        # Try to break at a sentence boundary
        cut_point = max_length - len(suffix)
        if cut_point <= 0:
            return text[:max_length]

        # Find last sentence/paragraph boundary
        for sep in ['\n\n', '\n', '。', '．', '. ']:
            idx = text.rfind(sep, 0, cut_point)
            if idx > cut_point * 0.5:  # Only if we keep at least 50%
                return text[:idx + len(sep)] + suffix
        
        return text[:cut_point] + suffix


def _render_text_table(rows: list) -> list:
    """Render table rows as aligned plain text."""
    if not rows:
        return []

    # Calculate column widths
    num_cols = max(len(row) for row in rows)
    col_widths = [0] * num_cols
    for row in rows:
        for i, cell in enumerate(row):
            if i < num_cols:
                col_widths[i] = max(col_widths[i], len(cell))

    # Format rows
    result = []
    for i, row in enumerate(rows):
        parts = []
        for j in range(num_cols):
            cell = row[j] if j < len(row) else ""
            parts.append(cell.ljust(col_widths[j]))
        line = "  ".join(parts).rstrip()
        result.append(line)
        if i == 0:
            # Add separator after header
            result.append("  ".join("-" * w for w in col_widths))

    return result
