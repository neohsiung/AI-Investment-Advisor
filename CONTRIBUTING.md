# Contributing

AI Investment Advisor is maintained by [Litov](https://litov.app). The repo follows Litov's shared development standard; the rules every change must meet are in [AGENTS.md](AGENTS.md) (the `DEV-STANDARD` block) and [.dev-standard/STANDARD.md](.dev-standard/STANDARD.md).

## Before you start

- **Security issues:** do not open a public issue. Email support@litov.app as described in [SECURITY.md](SECURITY.md).
- **Large changes:** open an issue first so we can agree on the approach.
- **Money-moving paths are closed to outside changes.** Trading, the risk gateway, capital policy and the broker service (listed in [.github/CODEOWNERS](.github/CODEOWNERS)) only change through a maintainer-written design doc.

## Workflow

1. Fork, then create a branch: `feat/…`, `fix/…`, `docs/…`, `refactor/…`, `test/…`, `chore/…` or `ci/…`.
2. Install the hooks once: `pre-commit install`. They run two secret scanners and size checks; do not bypass them with `--no-verify`.
3. Write a failing test first, then the change. Run `pytest tests/ -x --tb=short`.
4. One logical change per commit, with its tests. Format: `type(scope): summary`. Maintainers write the summary in Traditional Chinese; English is fine for outside contributors.
5. Open a pull request with the template. The first line is the risk level `R0`–`R3`; R2 changes (config, prompts, schema, migrations, deploy, hooks) need a command that proves the behaviour.

## 中文摘要

- 資安問題寄 support@litov.app，不要開公開 issue。
- 動到錢的路徑（交易、風險閘道、資金政策、券商服務）不接受外部修改。
- 分支、commit、PR 規則照 [AGENTS.md](AGENTS.md) 的開發辦法；先寫會失敗的測試，`pre-commit install` 後不要用 `--no-verify`。
