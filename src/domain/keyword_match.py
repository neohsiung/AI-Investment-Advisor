"""Risk keyword matching: the one rule for "does this keyword appear in this text".
風險關鍵字比對：「這個關鍵字有沒有出現在這段文字裡」的唯一規則。

Every Sentinel scoring path (ticker news, global events, contains_risk) calls this, so the rule lives in one place.
哨兵所有評分路徑（個股新聞、全球事件、contains_risk）都呼叫這裡，規則只寫一次。
"""
from __future__ import annotations


def keyword_in_text(keyword: str, text: str) -> bool:
    """True when ``keyword`` appears in ``text`` (case-insensitive).
    關鍵字出現在文字中時回傳 True（不分大小寫）。"""
    if not keyword:
        return False
    return keyword.lower() in text.lower()
