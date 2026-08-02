# AI Investment Advisor

> 🧠 自律型クオンツ投資プラットフォーム — 7エージェントスウォームによるフラクタルディベート、3層LLMルーティング、eToro自動売買。

<p align="center">
  <a href="https://github.com/neohsiung/AI-Investment-Advisor/stargazers"><img src="https://img.shields.io/github/stars/neohsiung/AI-Investment-Advisor?style=social" alt="Stars"></a>
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

---

## 📌 概要

AI Investment Advisor は、トップクラスのヘッジファンドの意思決定アーキテクチャを再現した自律型クオンツ投資プラットフォームです。**CIO エージェント**が投資課題を分解し、**7つの専門サブエージェント**に委任。独自の**フラクタルディベート**アルゴリズムでモデルの幻覚を排除し、eToro API を通じて自動的に取引を実行します。

---

## ✨ 主な機能

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>🧬 フラクタルディベート</h3>
      <p>マルチエージェント対抗推論により、単一モデルの幻覚を排除。</p>
    </td>
    <td width="50%" valign="top">
      <h3>🦅 10次元センチネル</h3>
      <p>VIX、価格、ニュース、マクロ、配分ドリフト — 自律型リスク監視レーダー。</p>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3>⚡ 自動ヘッジ</h3>
      <p>ミリ秒精度のポジション清算を eToro API で自動実行。</p>
    </td>
    <td width="50%" valign="top">
      <h3>🧠 OpenClaw アーキテクチャ</h3>
      <p>エージェントごとに独立した WAL でコンテキストオーバーフローを防止。</p>
    </td>
  </tr>
</table>

---

## 🚀 クイックスタート

```bash
git clone https://github.com/neohsiung/AI-Investment-Advisor.git
cd AI-Investment-Advisor
cp .env.example .env
./start.sh
```

| サービス | URL |
|:---------|:----|
| Next.js ダッシュボード | [http://localhost:3000](http://localhost:3000) |
| FastAPI / MCP Server | [http://localhost:8000](http://localhost:8000) |

---

## 📄 ライセンス

- **ライセンス**: [Apache License 2.0](../LICENSE)
- **免責事項**: 本ソフトウェアは市場を自律的に分析し、実際のブローカー認証情報を設定すると実際の資金で取引を行う可能性があります。投資アドバイスではなく、いかなる保証もなく「現状のまま」提供されます。詳細は [NOTICE](../NOTICE) を参照してください。

---

<p align="center">Built with ❤️ for Modern Quantitative Investing</p>
