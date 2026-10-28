# AI Investment Advisor

<p align="center">
  <a href="https://github.com/neohsiung/AI-Investment-Advisor"><img src="https://img.shields.io/github/stars/neohsiung/AI-Investment-Advisor?style=social" alt="Stars"></a>
  <a href="https://github.com/neohsiung/AI-Investment-Advisor/network/members"><img src="https://img.shields.io/github/forks/neohsiung/AI-Investment-Advisor?style=social" alt="Forks"></a>
  <a href="https://github.com/neohsiung/AI-Investment-Advisor/blob/main/LICENSE"><img src="https://img.shields.io/github/license/neohsiung/AI-Investment-Advisor" alt="License"></a>
</p>

<p align="center">
  <a href="https://github.com/neohsiung/AI-Investment-Advisor/blob/main/README.md">English</a> |
  <a href="https://github.com/neohsiung/AI-Investment-Advisor/blob/main/READMEs/README.zh-TW.md">繁體中文</a> |
  <strong>日本語</strong>
</p>

<p align="center">
  <img src="../assets/hero.png" alt="AI Investment Advisor" width="800" />
</p>

> [!WARNING]
> **投資アドバイスではありません。資金のあるブローカー口座につなぐと、実際のお金で取引します。** 実際のブローカー認証情報を設定すると、実際の注文を出します。現状のまま、いかなる保証もなく提供されます（[LICENSE](../LICENSE) と [NOTICE](../NOTICE) を参照）。このプロジェクトの `TRADING_MODE=paper` はシミュレーションではありません。eToro のトークンに demo 権限がないため、すべてのブローカー呼び出しが `InsufficientPermissions` で失敗します。安全なブレーキは `ai_trading_enabled=false` と `tradable_capital_pct=0` です。資金のある口座につなぐ前に、コードを読んでください。

AI Investment Advisor は、自分でホストして使うクオンツ投資システムです。複数の LLM エージェントが取引案を評価し、決定は決定論的なコードが行い、注文は eToro の実口座に送れます。この種のシステムを調べたい開発者で、リスクを自分で負える方向けです。

SPY に対して純超過リターンを出せるかどうかは、確認できていません。実際の数字は `/api/v1/net-alpha` と手元のデータベースで確認してください。

## 主な機能

| 項目 | 内容 |
|:-----|:-----|
| マルチエージェント討論 | LLM エージェントの評議会が銘柄ごとに並列で分析し、CIO エージェントが裁定します。構成は [`config/workflows/single_ticker_council.yaml`](../config/workflows/single_ticker_council.yaml) にあります。 |
| スコアリング | 買いは加重アンサンブルで採点し、売りは別に採点します。LLM は提案だけで、決定はコードが行います。 |
| レジーム | 3 状態の隠れマルコフモデルで相場の状態を推定し、現金比率と目標ベータを調整します。 |
| テールリスク | 極値理論（POT と一般化パレート分布）で 99.9% の VaR と CVaR を外挿します。 |
| リスクエンジン | ボラティリティ・ターゲット、相関クラスタリング、機会費用のハードル、分数ケリー、多因子アルファの合成。 |
| 執行 | 平均日次出来高に対する流動性の上限、ランダム化した TWAP と VWAP の分割、インプリメンテーション・ショートフォールの帰属、Almgren-Chriss モデルのオンライン較正。 |
| ダッシュボード | `/adaptive` に 5 つの観点のヘルスレーダーを表示し、各数値の出どころを示します。データがなければ、ないと表示します。 |

## クイックスタート

```bash
git clone https://github.com/neohsiung/AI-Investment-Advisor.git
cd AI-Investment-Advisor
cp .env.example .env
./start.sh
```

| サービス | URL |
|:---------|:----|
| ゲートウェイ (nginx、本番のみ) | [http://127.0.0.1:8088](http://127.0.0.1:8088) |
| Next.js ダッシュボード | [http://localhost:3001](http://localhost:3001) |
| FastAPI / MCP Server | [http://localhost:8000](http://localhost:8000)（dev は 8001）|
| SigNoz APM（`OBSERVABILITY=1 ./start.sh up` で起動した場合のみ） | [http://127.0.0.1:8080](http://127.0.0.1:8080) |

dev 環境の nginx はホストポートを公開していません。上記のフロントエンドと API のポートに直接アクセスしてください。ゲートウェイは本番のみです。

セルフホストと運用の説明は[ドキュメント索引](../docs/README.md)にあります。

## ライセンスと連絡先

- メンテナー: Litov。お問い合わせと脆弱性報告は support@litov.app へ（[SECURITY.md](../SECURITY.md) 参照）。サポートページ: <https://support.litov.app/>
- ライセンス: [Apache License 2.0](../LICENSE)
- 免責事項: 本ソフトウェアは金融市場を分析し、実際のブローカー認証情報を設定すると実際の資金で取引する可能性があります。投資アドバイスではなく、いかなる保証もなく現状のまま提供されます。詳細は [NOTICE](../NOTICE) を参照してください。

Apache License 2.0、Copyright Litov and contributors。
