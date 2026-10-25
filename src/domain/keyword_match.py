"""Risk keyword matching: the one rule for "does this keyword appear in this text".
風險關鍵字比對：「這個關鍵字有沒有出現在這段文字裡」的唯一規則。

Every Sentinel scoring path (ticker news, global events, contains_risk) calls this, so the rule lives in one place.
哨兵所有評分路徑（個股新聞、全球事件、contains_risk）都呼叫這裡，規則只寫一次。

Rule (DD-2026-1025-sentinel-keyword-word-boundary):
- Whole word, case-insensitive. A keyword next to an ASCII letter or digit is part of another word and does not
  match ('es' in 'Names', 'close' in 'disclosed'). Before 2026-10-25 this was a substring test, which let two-letter
  keywords hit nearly every headline and trigger a council each time.
- A keyword of PLURAL_MIN_LEN or more characters that ends in an ASCII letter also matches with a trailing 's' or
  'es' ('tariff' → 'tariffs'), so whole-word matching does not lose plural headlines.
- Only ASCII letters and digits count as word characters, so CJK keywords still match inside CJK text.
規則：整詞、不分大小寫；緊鄰 ASCII 字母或數字就視為別的字的一部分，不算命中。三個字元以上、結尾是英文字母的關鍵字，
加 s／es 的複數形也算命中。只有 ASCII 字母數字算字元，所以中文關鍵字在中文句子裡照樣命中。
"""
from __future__ import annotations

import re
from functools import lru_cache

PLURAL_MIN_LEN = 3

_BEFORE = r"(?<![a-z0-9])"
_AFTER = r"(?![a-z0-9])"


@lru_cache(maxsize=4096)
def _pattern(keyword: str) -> "re.Pattern[str]":
    kw = keyword.lower()
    plural = r"(?:e?s)?" if len(kw) >= PLURAL_MIN_LEN and kw[-1].isascii() and kw[-1].isalpha() else ""
    return re.compile(_BEFORE + re.escape(kw) + plural + _AFTER)


def keyword_in_text(keyword: str, text: str) -> bool:
    """True when ``keyword`` appears in ``text`` as a whole word (case-insensitive).
    關鍵字以整詞出現在文字中時回傳 True（不分大小寫）。"""
    if not keyword or not text:
        return False
    return _pattern(keyword).search(text.lower()) is not None
