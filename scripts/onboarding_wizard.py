#!/usr/bin/env python3
"""
scripts/onboarding_wizard.py — First-run onboarding wizard for investment-advisor.

Allows configuring the operating cost profile (Frugal / Balanced / Aggressive)
and the primary LLM provider credentials via an interactive CLI or scriptable flags.

Usage:
    python scripts/onboarding_wizard.py [--profile frugal|balanced|aggressive]
                                       [--provider openrouter|ollama|openai]
                                       [--api-key KEY]
                                       [--base-url URL]
                                       [--non-interactive]
"""
import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config.owner import get_owner_id
from src.services.cost_profile_service import CostProfileService, COST_PROFILES
from src.services.llm_provider_service import LLMProviderService


def print_banner():
    print("""
╔═══════════════════════════════════════════════════════════════════════╗
║         AI Investment Advisor — First-Run Onboarding Setup            ║
╚═══════════════════════════════════════════════════════════════════════╝
    """)


def prompt_choice(prompt_text: str, choices: list, default_idx: int = 0) -> str:
    print(f"\n{prompt_text}")
    for idx, (val, desc) in enumerate(choices, 1):
        def_tag = " (Default)" if (idx - 1) == default_idx else ""
        print(f"  [{idx}] {val}{def_tag}: {desc}")

    while True:
        try:
            choice = input(f"\nSelect an option [1-{len(choices)}] (Enter for default): ").strip()
            if not choice:
                return choices[default_idx][0]
            choice_int = int(choice)
            if 1 <= choice_int <= len(choices):
                return choices[choice_int - 1][0]
        except (ValueError, EOFError):
            pass
        print(f"Invalid selection. Please enter a number between 1 and {len(choices)}.")


def run_interactive(owner_id: str, cost_service: CostProfileService, provider_service: LLMProviderService):
    print_banner()

    print("Step 1: Select Operating Cost Profile (運算成本方案)")
    print("This controls how often background agents scan markets and the LLM budget tier.")

    cost_choices = [
        ("balanced", "15-min sentinel scans, smart reasoning for councils (~$15-25/wk)"),
        ("frugal", "30-min sentinel scans, nano-first lightweight models (~$2-5/wk, or $0 with Ollama)"),
        ("aggressive", "5-min sentinel scans, deep multi-tier analysis (~$50-100/wk)"),
    ]
    selected_profile = prompt_choice("Choose your cost profile:", cost_choices, default_idx=0)

    print("\nStep 2: Configure Primary LLM Provider (主要 AI 模型提供商)")
    print("The system swarms require an LLM to generate insights and execute workflows.")

    provider_choices = [
        ("openrouter", "OpenRouter (Recommended: single key for Claude, GPT, Llama, and open models)"),
        ("ollama", "Ollama (Local LLM server running on your machine, $0 API spend)"),
        ("openai", "OpenAI (Direct GPT-4o / o3-mini access)"),
        ("skip", "Skip for now (configure later in Settings -> AI Engine)"),
    ]
    selected_provider = prompt_choice("Choose primary provider:", provider_choices, default_idx=0)

    api_key = None
    base_url = None

    if selected_provider == "openrouter":
        print("\nEnter your OpenRouter API Key (e.g. sk-or-v1-...):")
        try:
            api_key = input("API Key (leave blank to skip): ").strip() or None
        except EOFError:
            api_key = None
    elif selected_provider == "ollama":
        print("\nEnter your Ollama Base URL:")
        try:
            default_url = "http://host.docker.internal:11434"
            entered_url = input(f"Base URL (Enter for '{default_url}'): ").strip()
            base_url = entered_url if entered_url else default_url
        except EOFError:
            base_url = "http://host.docker.internal:11434"
    elif selected_provider == "openai":
        print("\nEnter your OpenAI API Key (e.g. sk-...):")
        try:
            api_key = input("API Key (leave blank to skip): ").strip() or None
        except EOFError:
            api_key = None

    apply_configuration(owner_id, cost_service, provider_service, selected_profile, selected_provider, api_key, base_url)


def apply_configuration(owner_id: str, cost_service: CostProfileService, provider_service: LLMProviderService,
                        profile: str, provider_code: str, api_key: str = None, base_url: str = None):
    print("\nApplying configuration...")

    # 1. Cost Profile
    if profile in COST_PROFILES:
        res = cost_service.apply_profile(profile)
        print(f"  ✓ Cost profile applied: {res['name']} ({res['sentinel_tick_minute']})")
    else:
        print(f"  ⚠️ Unknown cost profile '{profile}', skipped.")

    # 2. LLM Provider
    if provider_code and provider_code != "skip":
        providers = provider_service.list()
        existing = next((p for p in providers if p["provider_code"] == provider_code), None)
        patch = {"enabled": True}
        if api_key:
            patch["api_key"] = api_key
        if base_url:
            patch["base_url"] = base_url

        if existing:
            provider_service.update(existing["id"], patch)
            print(f"  ✓ Updated provider '{provider_code}'")
        else:
            provider_service.create({
                "provider_code": provider_code,
                "display_name": provider_code.title(),
                "api_key": api_key,
                "base_url": base_url,
                "enabled": True,
            })
            print(f"  ✓ Created provider '{provider_code}'")

    print("\n✅ Onboarding complete! Open http://127.0.0.1:8088 to access the dashboard.\n")


def main():
    parser = argparse.ArgumentParser(description="First-Run Onboarding Wizard for Investment Advisor")
    parser.add_argument("--profile", choices=["frugal", "balanced", "aggressive"], help="Operating cost profile")
    parser.add_argument("--provider", choices=["openrouter", "ollama", "openai", "skip"], help="Primary LLM provider")
    parser.add_argument("--api-key", help="API key for chosen provider")
    parser.add_argument("--base-url", help="Base URL (e.g. for Ollama)")
    parser.add_argument("--non-interactive", action="store_true", help="Run without interactive prompts")

    args = parser.parse_args()

    owner_id = get_owner_id()
    cost_service = CostProfileService(user_id=owner_id)
    provider_service = LLMProviderService(user_id=owner_id)

    is_interactive = sys.stdin.isatty() and not args.non-interactive

    if is_interactive and not args.profile and not args.provider:
        run_interactive(owner_id, cost_service, provider_service)
    else:
        profile = args.profile or "balanced"
        provider = args.provider or "skip"
        apply_configuration(owner_id, cost_service, provider_service, profile, provider, args.api_key, args.base_url)


if __name__ == "__main__":
    main()
