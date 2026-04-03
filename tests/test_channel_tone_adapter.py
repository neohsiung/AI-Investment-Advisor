"""
Tests for ChannelToneAdapter — Task 5B-4.
"""
import pytest
from src.agents.persona.channel_tone_adapter import ChannelToneAdapter, ToneConfig


class TestChannelToneAdapter:
    def setup_method(self):
        self.adapter = ChannelToneAdapter()

    def test_strip_markdown(self):
        adapter = ChannelToneAdapter({"custom": ToneConfig(use_markdown=False)})
        text = "**Bold** text and *italic* or _italic_ and `code`"
        result = adapter.adapt(text, "custom")
        assert "Bold text and italic or italic and code" in result

    def test_strip_markdown_links_images(self):
        adapter = ChannelToneAdapter({"custom": ToneConfig(use_markdown=False)})
        text = "Here is a [link](http://example.com) and an image ![alt text](img.png)"
        result = adapter.adapt(text, "custom")
        assert "Here is a link and an image [alt text]" in result

    def test_remove_emoji(self):
        adapter = ChannelToneAdapter({"custom": ToneConfig(use_emoji=False)})
        text = "Hello 🌍🚀! How are you 😃?"
        result = adapter.adapt(text, "custom")
        assert result == "Hello ! How are you ?"

    def test_table_conversion_to_text(self):
        adapter = ChannelToneAdapter({"custom": ToneConfig(table_format="text")})
        table = (
            "| Header 1 | Header 2 |\n"
            "|---|---|\n"
            "| Data A | Data B |\n"
            "| Longer Data | C |\n"
        )
        result = adapter.adapt(table, "custom")
        # Should align columns
        assert "Header 1     Header 2" in result
        assert "-----------  --------" in result
        assert "Longer Data  C" in result
        assert "|" not in result

    def test_remove_tables(self):
        adapter = ChannelToneAdapter({"custom": ToneConfig(table_format="none")})
        text = (
            "Intro\n"
            "| Col |\n"
            "|---|\n"
            "| val |\n"
            "Outro"
        )
        result = adapter.adapt(text, "custom")
        assert "Intro" in result
        assert "Outro" in result
        assert "Col" not in result

    def test_truncation(self):
        suffix = "\n(Truncated)"
        adapter = ChannelToneAdapter({"custom": ToneConfig(max_length=20, truncation_suffix=suffix)})
        text = "This is a very long text that must be cut"
        result = adapter.adapt(text, "custom")
        
        assert len(result) <= 20
        assert suffix in result
        assert result.endswith(suffix)

    def test_line_defaults(self):
        # LINE config strips markdown and uses text tables
        text = "**Bold**\n| A |\n|---|\n| B |"
        result = self.adapter.adapt(text, "line")
        assert "Bold" in result
        assert "**Bold**" not in result
        assert "|" not in result  # Table converted

    def test_web_defaults(self):
        # Web config removes emoji
        text = "Hello 🌍"
        result = self.adapter.adapt(text, "web")
        assert result == "Hello"

    def test_telegram_defaults(self):
        # Telegram keeps most things as is
        text = "**Bold** | A |\n|---|\n| B | 🚀"
        result = self.adapter.adapt(text, "telegram")
        assert "**Bold**" in result
        assert "|" in result
        assert "🚀" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
