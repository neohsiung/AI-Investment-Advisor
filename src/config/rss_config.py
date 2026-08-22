"""
Unified RSS News Sources Configuration.
各區域重點財經 RSS 來源設定，供 n8n 動態抓取與 Sentinel 監控。
"""

RSS_SOURCES = [
    # --- North America (美國/加拿大) ---
    {
        "id": "bloomberg_markets",
        "name": "Bloomberg Markets",
        "url": "https://feeds.bloomberg.com/markets/news.rss",
        "region": "US",
        "category": "Markets"
    },
    {
        "id": "cnbc_business",
        "name": "CNBC Business",
        "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "region": "US",
        "category": "Business"
    },
    {
        "id": "reuters_business",
        "name": "Reuters Business",
        "url": "https://feeds.reuters.com/reuters/businessNews",
        "region": "US",
        "category": "Business"
    },
    {
        "id": "wsj_markets",
        "name": "Wall Street Journal Markets",
        "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "region": "US",
        "category": "Markets"
    },
    {
        "id": "yahoo_finance",
        "name": "Yahoo Finance",
        "url": "https://finance.yahoo.com/news/rssindex",
        "region": "US",
        "category": "Finance"
    },
    {
        "id": "financial_post",
        "name": "Financial Post",
        "url": "https://financialpost.com/feed/",
        "region": "CA",
        "category": "Business"
    },

    # --- Europe (歐洲/英國) ---
    {
        "id": "ft_main",
        "name": "Financial Times",
        "url": "https://www.ft.com/?format=rss",
        "region": "UK",
        "category": "Global Finance"
    },
    {
        "id": "euronews_business",
        "name": "Euronews Business",
        "url": "https://www.euronews.com/rss?level=theme&name=news",
        "region": "EU",
        "category": "Business"
    },
    {
        "id": "les_echos",
        "name": "Les Echos",
        "url": "https://www.lesechos.fr/rss/finance-marches.xml",
        "region": "FR",
        "category": "Finance"
    },
    {
        "id": "handelsblatt",
        "name": "Handelsblatt",
        "url": "https://www.handelsblatt.com/contentexport/feed/schlagzeilen",
        "region": "DE",
        "category": "Business"
    },
    {
        "id": "di_se",
        "name": "Dagens Industri",
        "url": "https://www.di.se/rss",
        "region": "SE",
        "category": "Business"
    },
    {
        "id": "swissinfo_finance",
        "name": "SwissInfo Finance",
        "url": "https://www.swissinfo.ch/eng/rss?siteSect=3",
        "region": "CH",
        "category": "Finance"
    },
    {
        "id": "il_sole_24_ore",
        "name": "Il Sole 24 Ore",
        "url": "https://www.ilsole24ore.com/rss/finanza-e-mercati.xml",
        "region": "IT",
        "category": "Finance"
    },

    # --- Asia Pacific (亞太地區) ---
    {
        "id": "nikkei_asia",
        "name": "Nikkei Asia",
        "url": "https://asia.nikkei.com/rss/feed/nar",
        "region": "JP",
        "category": "Business"
    },
    {
        "id": "nhk_world_business",
        "name": "NHK World Business",
        "url": "https://www3.nhk.or.jp/rss/news/cat5.xml",
        "region": "JP",
        "category": "Business"
    },
    {
        "id": "xinhua_business",
        "name": "Xinhua Business",
        "url": "http://www.news.cn/english/rss/businessrss.xml",
        "region": "CN",
        "category": "Business"
    },
    {
        "id": "thepaper_finance",
        "name": "The Paper Business (澎湃新聞)",
        "url": "https://www.thepaper.cn/rss_newsList.jsp?nodeid=25489",
        "region": "CN",
        "category": "Finance"
    },
    {
        "id": "cna_finance",
        "name": "CNA Finance (中央社)",
        "url": "https://www.cna.com.tw/rss.aspx?type=finance",
        "region": "TW",
        "category": "Finance"
    },
    {
        "id": "business_weekly",
        "name": "Business Weekly (商業周刊)",
        "url": "https://www.businessweekly.com.tw/rss",
        "region": "TW",
        "category": "Business"
    },
    {
        "id": "economic_daily",
        "name": "Economic Daily (經濟日報)",
        "url": "https://money.udn.com/rssfeed/news/1001/5588",
        "region": "TW",
        "category": "Finance"
    },
    {
        "id": "hket_finance",
        "name": "HKET (香港經濟日報)",
        "url": "https://www.hket.com/rss",
        "region": "HK",
        "category": "Finance"
    },
    {
        "id": "businesstimes_sg",
        "name": "The Business Times",
        "url": "https://www.businesstimes.com.sg/rss",
        "region": "SG",
        "category": "Business"
    },
    {
        "id": "korea_herald_biz",
        "name": "Korea Herald Business",
        "url": "http://www.koreaherald.com/rss/020000000000.xml",
        "region": "KR",
        "category": "Business"
    },
    {
        "id": "economic_times_in",
        "name": "The Economic Times",
        "url": "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
        "region": "IN",
        "category": "Finance"
    },
    {
        "id": "jakarta_post_biz",
        "name": "Jakarta Post Business",
        "url": "https://www.thejakartapost.com/rss/business",
        "region": "ID",
        "category": "Business"
    },
    {
        "id": "australian_financial_review",
        "name": "Australian Financial Review",
        "url": "https://www.afr.com/rss",
        "region": "AU",
        "category": "Finance"
    },

    # --- Other Regions (其他地區) ---
    {
        "id": "valor_economico",
        "name": "Valor Econômico",
        "url": "https://valor.globo.com/rss/",
        "region": "BR",
        "category": "Finance"
    },
    {
        "id": "el_financiero",
        "name": "El Financiero",
        "url": "https://www.elfinanciero.com.mx/rss/portada.xml",
        "region": "MX",
        "category": "Finance"
    },
    {
        "id": "businesstech_za",
        "name": "BusinessTech",
        "url": "https://businesstech.co.za/news/feed/",
        "region": "ZA",
        "category": "Business"
    },

    # --- Global ---
    {
        "id": "investing_global",
        "name": "Investing.com Global",
        "url": "https://www.investing.com/rss/news.rss",
        "region": "Global",
        "category": "Markets"
    }
]

def get_rss_sources(user_id: str = None):
    sources = list(RSS_SOURCES)
    if user_id:
        try:
            from src.services.settings_service import SettingsService
            ss = SettingsService(user_id=user_id)
            custom_sources = ss.get_setting("custom_rss_sources")
            if custom_sources and isinstance(custom_sources, list):
                for item in custom_sources:
                    if isinstance(item, dict) and "url" in item:
                        sources.append({
                            "id": item.get("id", f"custom_{abs(hash(item['url'])) % 1000000}"),
                            "name": item.get("name", "Custom Feed"),
                            "url": item["url"],
                            "region": item.get("region", "Custom"),
                            "category": item.get("category", "Custom")
                        })
        except Exception:
            pass
    return sources
