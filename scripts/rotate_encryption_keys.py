#!/usr/bin/env python3
"""
Re-encrypt secrets at rest under a new key — the other half of a key rotation.

2026-08-20: `.env.bak-20260711` was committed in 3a7be7f0 with five live
secrets, two of which (`APP_SECRET_KEY`, `LLM_CREDENTIAL_KEY`) are the keys
that encrypt credentials at rest. Swapping them in `.env` alone does NOT
rotate them — it orphans every ciphertext in the database.

That failure is silent, not loud. `AlchemySettingsRepository._decrypt`
(settings_repository.py:155) catches the Fernet error, logs, and returns the
raw ciphertext, so `etoro_api_key` comes back as the literal string
"ENC:gAAAA..." and gets sent to eToro as if it were a credential. Nothing
crashes. This script exists so the swap is never done without the re-wrap.

Run with BOTH old and new keys present in the environment:

    APP_SECRET_KEY=<old>        APP_SECRET_KEY_NEW=<new>
    LLM_CREDENTIAL_KEY=<old>    LLM_CREDENTIAL_KEY_NEW=<new>

    python scripts/rotate_encryption_keys.py              # dry run (default)
    python scripts/rotate_encryption_keys.py --commit     # actually write

Only after this reports success should `.env` be updated to the new keys.

2026-08-20：`.env.bak-20260711` 曾把五個密鑰commit進版控，其中兩個是
靜態加密金鑰。只改 `.env` 不算輪換——資料庫裡的密文會全部變成孤兒，
且失敗是靜默的：_decrypt 會吞掉例外並原樣回傳密文，憑證看起來仍「有值」。
本腳本負責重新包裝，必須在新舊金鑰並存時執行。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, List, NamedTuple, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from cryptography.fernet import Fernet  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from src.data.database import get_db_engine  # noqa: E402
from src.data.models import LLMProvider, Setting  # noqa: E402
from src.repositories.settings_repository import AlchemySettingsRepository  # noqa: E402


SETTINGS_PREFIX = "ENC:"
FERNET_PREFIX = "FERN:"
FALLBACK_PREFIX = "B64H:"


class RotationError(RuntimeError):
    """Any condition that must abort the whole batch."""


class Row(NamedTuple):
    """One ciphertext to re-wrap, plus how to put it back where it came from."""
    label: str              # human-readable, safe to print (never the value)
    ciphertext: str         # unwrapped, prefix included
    apply: Callable[[str], None]   # writes the new ciphertext onto the ORM object


class KeyRing(NamedTuple):
    """
    Which (old, new) key pair rotates which prefix.

    Keyed by prefix rather than by table, because a nested value carries
    layers of both kinds — prod's ENC(FERN(key)) needs APP_SECRET_KEY for the
    outer layer and LLM_CREDENTIAL_KEY for the inner one.
    以前綴而非資料表為索引：巢狀值同時含兩種層級，外層用 APP_SECRET_KEY、
    內層用 LLM_CREDENTIAL_KEY。
    """
    rotatable: dict         # prefix -> (old Fernet, new Fernet)


# ----------------------------------------------------------------------
# JSON-column quoting
# ----------------------------------------------------------------------
# `Setting.value` is Column(JSON) (models.py:79) and history has left some
# rows double-serialised — the stored JSON is the *string* '"ENC:gAAA..."',
# quotes included. `_decrypt` copes by stripping them
# (settings_repository.py:134). We must too, but we also have to write back
# in the SAME shape we found, or a "fix" here becomes a data migration
# nobody asked for.
# Setting.value 是 JSON 欄位，歷史資料中有被重複序列化、連引號一起存進去的值；
# 讀取時要剝掉，寫回時必須維持原本的形狀，否則等於偷偷做了一次資料遷移。
def _unwrap(value: str) -> Tuple[str, bool]:
    """Return (inner, was_quoted)."""
    stripped = value.strip()
    if len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"'):
        return stripped[1:-1], True
    return value, False


def _rewrap(value: str, was_quoted: bool) -> str:
    return f'"{value}"' if was_quoted else value


# ----------------------------------------------------------------------
# Key loading
# ----------------------------------------------------------------------
def _load_key_pair(env_name: str) -> Tuple[Fernet, Fernet]:
    """Build (old, new) Fernet from `<NAME>` and `<NAME>_NEW`. Fail loudly."""
    old_raw = os.getenv(env_name)
    new_raw = os.getenv(f"{env_name}_NEW")

    missing = [n for n, v in ((env_name, old_raw), (f"{env_name}_NEW", new_raw)) if not v]
    if missing:
        raise RotationError(
            f"{', '.join(missing)} not set. Both the old and the new key must be "
            f"present at once — that is what makes this script able to decrypt "
            f"with one and re-encrypt with the other."
        )

    if old_raw == new_raw:
        raise RotationError(
            f"{env_name} and {env_name}_NEW are identical. Generate a new key: "
            f'python -c "from cryptography.fernet import Fernet; '
            f'print(Fernet.generate_key().decode())"'
        )

    try:
        old = Fernet(old_raw.encode())
    except Exception as exc:
        raise RotationError(f"{env_name} is not a valid Fernet key: {exc}") from exc
    try:
        new = Fernet(new_raw.encode())
    except Exception as exc:
        raise RotationError(f"{env_name}_NEW is not a valid Fernet key: {exc}") from exc

    return old, new


# ----------------------------------------------------------------------
# Re-wrap
# ----------------------------------------------------------------------
MAX_NESTING = 4


def _reencrypt(ciphertext: str, keys: "KeyRing", label: str, depth: int = 1) -> Tuple[str, int]:
    """
    Re-wrap a ciphertext onto the new keys, preserving its exact structure.
    Returns (new_ciphertext, layers_rotated).

    Nesting is real. `settings.openrouter_api_key` in production holds
    ENC(FERN(key)) — an ENC: layer wrapping a whole FERN: ciphertext, which
    `llm_config_chain.py:236-245` recognises and rejects, so the value has sat
    there unused since 2026-07-11.

    Both layers are key-bound, so both must be rotated. Peeling only the outer
    one would leave the inner sealed under a key we are retiring — the exact
    silent breakage this script exists to prevent. Unwrapping fully would be
    worse: it would turn a value the application currently ignores into one it
    starts using, which is a behavioural change smuggled inside a security fix.
    So each layer is decrypted with its own old key and re-sealed with its own
    new key, and the shape comes back out identical.
    巢狀加密確實存在（prod 的 openrouter_api_key 即 ENC(FERN(key))，
    自 2026-07-11 起被 llm_config_chain 的 guard 忽略）。兩層都綁著金鑰，
    故兩層都要輪換：只剝外層會讓內層留在退役金鑰上；完全拆開則會讓原本被
    忽略的值變成生效值——那是把行為變更夾帶進安全修復。因此逐層以各自的
    新舊金鑰重封，結構原樣還原。

    Aborts the batch rather than guess when the old key cannot open a layer.
    """
    prefix = next((p for p in keys.rotatable if ciphertext.startswith(p)), None)
    if prefix is None:
        raise RotationError(f"{label}: not a rotatable ciphertext (depth {depth}).")

    if depth > MAX_NESTING:
        raise RotationError(
            f"{label}: nested more than {MAX_NESTING} layers deep. Refusing to "
            f"recurse further. Nothing has been written."
        )

    old, new = keys.rotatable[prefix]
    token = ciphertext[len(prefix):]

    try:
        plaintext = old.decrypt(token.encode()).decode("utf-8")
    except Exception as exc:
        raise RotationError(
            f"{label}: cannot decrypt the {prefix.rstrip(':')} layer at depth "
            f"{depth} with the current key ({type(exc).__name__}). Either the "
            f"wrong old key is in the environment, or this layer was encrypted "
            f"under a third key. Nothing has been written."
        ) from exc

    layers = 1
    if plaintext.startswith(tuple(keys.rotatable)):
        # Another key-bound ciphertext inside. Recurse so it is rotated too.
        plaintext, inner_layers = _reencrypt(plaintext, keys, label, depth + 1)
        layers += inner_layers
    elif plaintext.startswith(FALLBACK_PREFIX):
        # B64H: is keyless obfuscation (llm_credential_cipher.py:85-89) — there
        # is no key to move it onto, so it rides along as opaque payload.
        # B64H: 是無金鑰編碼，沒有金鑰可換，原樣當作內容一起重封。
        pass

    return f"{prefix}{new.encrypt(plaintext.encode('utf-8')).decode('utf-8')}", layers


# ----------------------------------------------------------------------
# Collection
# ----------------------------------------------------------------------
def _collect_settings(session, should_encrypt: Callable[[str], bool]) -> Tuple[List[Row], List[str]]:
    """
    Gather every `settings` row holding an ENC: value.

    Driven by the value's prefix, not by `_should_encrypt(key)`. A row whose
    key no longer matches the sensitive-name patterns can still hold a real
    ciphertext from when it did, and skipping it would leave a blob encrypted
    under a dead key — invisible until something reads it. `_should_encrypt`
    is still consulted, but only to report the mismatch.
    以「值的前綴」而非「鍵名」決定要處理哪些列：鍵名規則變動過的舊列同樣
    可能存著真密文，漏掉就會留下綁在死金鑰上的孤兒。_should_encrypt 僅用於
    回報不一致，不用於篩選。
    """
    rows: List[Row] = []
    notes: List[str] = []

    for setting in session.query(Setting).all():
        raw = setting.value
        if not isinstance(raw, str):
            continue

        inner, was_quoted = _unwrap(raw)
        if not inner.startswith(SETTINGS_PREFIX):
            if inner.startswith((FERNET_PREFIX, FALLBACK_PREFIX)):
                notes.append(
                    f"settings[{setting.key}] holds a "
                    f"{inner.split(':')[0]}: value, not ENC: — left untouched"
                )
            continue

        label = f"settings[{setting.key}] user={str(setting.user_id)[:8]}"
        if not should_encrypt(setting.key):
            notes.append(
                f"{label}: encrypted although its name no longer matches the "
                f"sensitive-key patterns — rotating it anyway"
            )

        def apply(new_ct: str, _s=setting, _q=was_quoted) -> None:
            _s.value = _rewrap(new_ct, _q)

        rows.append(Row(label=label, ciphertext=inner, apply=apply))

    return rows, notes


def _collect_providers(session) -> Tuple[List[Row], List[str]]:
    """Gather every `llm_providers.encrypted_api_key` holding a FERN: value."""
    rows: List[Row] = []
    notes: List[str] = []

    for provider in session.query(LLMProvider).all():
        raw = provider.encrypted_api_key
        if not isinstance(raw, str) or not raw:
            continue

        label = f"llm_providers[{provider.provider_code}/{provider.display_name}]"

        if raw.startswith(FALLBACK_PREFIX):
            # B64H: is the no-key fallback (llm_credential_cipher.py:85-89) —
            # obfuscation, not encryption, and not tied to either key.
            # B64H: 是無金鑰時的退化編碼，與金鑰無關，輪換不需處理。
            notes.append(f"{label}: B64H: fallback value, not key-bound — left untouched")
            continue
        if raw.startswith(SETTINGS_PREFIX):
            notes.append(f"{label}: holds an ENC: value in a FERN: column — left untouched")
            continue
        if not raw.startswith(FERNET_PREFIX):
            notes.append(f"{label}: plaintext or legacy value — left untouched")
            continue

        def apply(new_ct: str, _p=provider) -> None:
            _p.encrypted_api_key = new_ct

        rows.append(Row(label=label, ciphertext=raw, apply=apply))

    return rows, notes


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def rotate(commit: bool, engine=None) -> int:
    engine = engine or get_db_engine()

    app_old, app_new = _load_key_pair("APP_SECRET_KEY")
    llm_old, llm_new = _load_key_pair("LLM_CREDENTIAL_KEY")
    keys = KeyRing(rotatable={
        SETTINGS_PREFIX: (app_old, app_new),
        FERNET_PREFIX: (llm_old, llm_new),
    })

    # Borrowed so the definition of "sensitive key name" lives in exactly one
    # place (settings_repository.py:112-116).
    should_encrypt = AlchemySettingsRepository(engine)._should_encrypt

    mode = "COMMIT" if commit else "DRY RUN"
    print(f"=== Encryption key rotation [{mode}] ===\n")

    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        setting_rows, setting_notes = _collect_settings(session, should_encrypt)
        provider_rows, provider_notes = _collect_providers(session)
        plan = setting_rows + provider_rows

        if not plan:
            print("Nothing to rotate: no ENC: or FERN: ciphertext found.")
            for note in setting_notes + provider_notes:
                print(f"  note: {note}")
            return 0

        # Re-encrypt everything before writing anything. A RotationError here
        # leaves the session untouched, so a bad row cannot half-rotate the DB.
        # 先全部重新加密再寫入；中途失敗時 session 未被觸碰，不會半套輪換。
        for row in plan:
            new_ct, layers = _reencrypt(row.ciphertext, keys, row.label)
            row.apply(new_ct)
            nested = f", {layers} nested layers" if layers > 1 else ""
            print(f"  re-wrapped {row.label}  "
                  f"(len {len(row.ciphertext)} -> {len(new_ct)}{nested})")

        print(
            f"\n{len(setting_rows)} settings, {len(provider_rows)} llm_providers "
            f"re-encrypted."
        )
        for note in setting_notes + provider_notes:
            print(f"  note: {note}")

        if commit:
            session.commit()
            print("\nCommitted. Now update .env to the new keys, drop the _NEW "
                  "lines, and restart api/worker_1/worker_2/beat.")
        else:
            session.rollback()
            print("\nDry run — nothing written. Re-run with --commit to apply.")
        return 0

    except RotationError as exc:
        session.rollback()
        print(f"\nABORTED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        session.rollback()
        print(f"\nABORTED (unexpected): {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-encrypt at-rest secrets from the old keys to the new ones.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually write. Without it the script only reports what it would do.",
    )
    args = parser.parse_args()

    try:
        return rotate(commit=args.commit)
    except RotationError as exc:
        print(f"ABORTED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
