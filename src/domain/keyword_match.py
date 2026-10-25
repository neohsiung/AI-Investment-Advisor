"""Risk keyword matching: the one rule for "does this keyword appear in this text".
風險關鍵字比對：「這個關鍵字有沒有出現在這段文字裡」的唯一規則。

Every Sentinel scoring path (ticker news, global events, contains_risk) calls this, so the rule lives in one place.
哨兵所有評分路徑（個股新聞、全球事件、contains_risk）都呼叫這裡，規則只寫一次。

Rule (DD-2026-1025-sentinel-keyword-word-boundary):
- Whole word, case-insensitive. A keyword next to an ASCII letter or digit is part of another word and does not
  match ('es' in 'Names', 'close' in 'disclosed'). Before 2026-10-25 this was a substring test, which let two-letter
  keywords hit nearly every headline and trigger a council each time.
- The start of the keyword must be a word start. How the end is matched depends on length, so whole-word matching
  does not lose inflected headlines:
  - STEM_MIN_LEN (5) or more characters ending in an ASCII letter: any trailing letters are allowed, so 'sanction'
    matches 'sanctioned' and 'bankrupt' matches 'bankruptcies'.
  - PLURAL_MIN_LEN (3) to 4 characters ending in an ASCII letter: an optional 's' or 'es' ('war' → 'wars').
  - Shorter keywords ('es', 'it'): the exact word only.
- Surrounding whitespace in a stored keyword is ignored; a blank keyword never matches.
- Only ASCII letters and digits count as word characters, so CJK keywords still match inside CJK text.
規則：不分大小寫，關鍵字開頭必須是詞的開頭。五個字元以上的英文關鍵字，詞尾可接任何字母（sanction → sanctioned）；
三到四個字元允許 s／es；更短的只比整詞。關鍵字前後空白忽略。
只有 ASCII 字母數字算字元，所以中文關鍵字在中文句子裡照樣命中。
"""
from __future__ import annotations

import re
from functools import lru_cache

PLURAL_MIN_LEN = 3
STEM_MIN_LEN = 5

_BEFORE = r"(?<![a-z0-9])"
_AFTER = r"(?![a-z0-9])"


def _suffix(kw: str) -> str:
    if not (kw[-1].isascii() and kw[-1].isalpha()):
        return ""
    if len(kw) >= STEM_MIN_LEN:
        return r"[a-z]*"
    if len(kw) >= PLURAL_MIN_LEN:
        return r"(?:e?s)?"
    return ""


@lru_cache(maxsize=4096)
def _pattern(keyword: str) -> "re.Pattern[str]":
    kw = keyword.strip().lower()
    return re.compile(_BEFORE + re.escape(kw) + _suffix(kw) + _AFTER)


def keyword_in_text(keyword: str, text: str) -> bool:
    """True when ``keyword`` appears in ``text`` starting at a word start (case-insensitive; see module rule).
    關鍵字從詞的開頭出現在文字中時回傳 True（不分大小寫；規則見模組說明）。"""
    if not keyword or not keyword.strip() or not text:
        return False
    return _pattern(keyword).search(text.lower()) is not None
