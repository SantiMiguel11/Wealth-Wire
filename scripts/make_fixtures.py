"""Generate the offline fixture site used by tests and the demo (tests/fixtures/demo/).

SYNTHETIC TEST DATA. The build environment could not reach the real outlets (egress proxy 403),
so these feeds imitate each outlet's *format* (RSS vs Atom, title case vs sentence case,
"| Outlet" suffixes, utm params, timezones, content:encoded) with invented stories.
Firm names are fictional except the four watchlist firms, which appear only in neutral stories.

Run: python scripts/make_fixtures.py
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "demo"
T0 = datetime(2026, 9, 25, 16, 0, tzinfo=timezone.utc)
NOTE = "SYNTHETIC TEST DATA - not real news"
LONG_HTML = (
    "<p>{d}</p><p>" + "Additional context paragraph with <strong>markup</strong> and &amp; entities. " * 8 + "</p>"
)

# (source, hours_before_T0, title, description). Deals and non-deals mixed: the pipeline keeps only deals.
S = "SEC Press Releases"
TA, WM, CW, FA, IN, RB, FP, AH, KI = (
    "ThinkAdvisor", "WealthManagement.com", "Citywire RIA", "Financial Advisor Magazine",
    "InvestmentNews", "RIABiz", "Financial Planning", "AdvisorHub", "Kitces",
)
PRN, SA, FT, PEH, TC = "PR Newswire M&A", "Seeking Alpha M&A", "Financial Times Companies", "PE Hub", "TechCrunch M&A"
BD, PD, IJ, RN, BPD, HD, FH, FB, FPH, RD, UD, SCD = (
    "Banking Dive", "Payments Dive", "Insurance Journal", "Reinsurance News", "BioPharma Dive", "Healthcare Dive",
    "Fierce Healthcare", "Fierce Biotech", "Fierce Pharma", "Retail Dive", "Utility Dive", "Supply Chain Dive",
)

STORIES: list[list[tuple[str, float, str, str]]] = [
    # --- wealth management and RIA deals ----------------------------------------------------------
    [
        (WM, 30, "Harborview Wealth Partners buys $1.2bn Summit Ridge Advisors", "The Denver-based consolidator adds a $1.2bn RIA with 14 advisors, its fifth deal this year."),
        (FP, 28, "Harborview Wealth Partners Acquires $1.2B Summit Ridge Advisors", "Summit Ridge Advisors, which manages $1.2 billion, will keep its brand and leadership team."),
        (IN, 26, "Harborview Wealth Partners to Acquire Summit Ridge Advisors, a $1.2 Billion RIA", "The deal is expected to close in the fourth quarter."),
        (RB, 20, "Harborview Wealth Partners scoops up Summit Ridge Advisors as its RIA buying spree continues", ""),
        (PRN, 27, "Harborview Wealth Partners Announces Acquisition of Summit Ridge Advisors, a $1.2 Billion Registered Investment Adviser",
         "SEATTLE -- Harborview Wealth Partners, a wealth management firm, today announced it has acquired Summit Ridge Advisors."),
    ],
    [
        (WM, 52, "Cedar Lane Private Wealth sells to Meridian Capital Partners", "Cedar Lane, an $850M RIA in Charlotte, becomes Meridian's first Southeast office."),
        (IN, 49, "Meridian Capital Partners adds $850M Cedar Lane Private Wealth", "Meridian Capital Partners continues its push into the Carolinas."),
    ],
    [
        (FP, 40, "Blue Heron Capital takes minority stake in Oakmont Family Office", "Oakmont oversees $2.3 billion for 60 ultra-high-net-worth families."),
    ],
    [
        (WM, 62, "Northgate Advisors and Pinecrest Wealth Merge to Form $4.5B Firm", "The combined firm will operate under the Northgate name."),
        (FP, 60, "Northgate Advisors and Pinecrest Wealth merge in $4.5 billion combination", "Both founders will serve as co-CEOs of the combined RIA."),
    ],
    [
        (IN, 18, "Lakeshore Financial Group agrees to be acquired by Atlas Wealth Management", "Lakeshore, with $640 million in assets, is Atlas's second Midwest deal."),
    ],
    [
        (IN, 70, "Atlas Wealth Management acquires Birchwood Row Advisory", "Atlas adds a $300M practice in Minneapolis."),
    ],
    [
        (WM, 22, "PE-Backed Crestline Wealth to Buy Riverbend Financial and Aspen Grove Advisors", "The two deals add a combined $1.9B in client assets."),
        (PRN, 21.5, "Crestline Wealth Completes Acquisition of Riverbend Financial, a $900 Million RIA",
         "DALLAS -- Crestline Wealth, a registered investment adviser, closed its acquisition of Riverbend Financial."),
    ],
    [
        (RB, 7, "Willowbrook Wealth lands minority investment from Bear Mountain Capital", ""),
    ],
    [
        (FP, 56, "Sequoia Point Wealth completes recapitalization with Granite Peak Partners", "The $2.8B firm says the deal gives next-generation advisors a path to equity."),
    ],
    # --- investment banking -----------------------------------------------------------------------
    [
        (PRN, 11, "Stonebridge Securities Acquires Boutique Investment Bank Calloway Partners", "NEW YORK -- Stonebridge Securities, a broker-dealer, acquired M&A advisory firm Calloway Partners."),
        (SA, 10, "Stonebridge Securities to acquire investment bank Calloway Partners", ""),
    ],
    # --- technology -------------------------------------------------------------------------------
    [
        (PRN, 34, "Northwind Software to Acquire Brightpath Analytics for $420 Million", "REDMOND -- Northwind Software, a maker of business software, will acquire Brightpath Analytics."),
        (TC, 33, "Northwind Software buys Brightpath Analytics for $420M", ""),
        (SA, 32, "Northwind Software to buy Brightpath Analytics in $420M deal", ""),
    ],
    [
        (TC, 15, "Quill AI is acquired by Ferrous Cloud", ""),
    ],
    # --- private equity / healthcare --------------------------------------------------------------
    [
        (PRN, 46, "Granite Peak Partners Completes Acquisition of Lumen Dental Group", "DENVER -- Granite Peak Partners, a private equity firm, completed its acquisition of Lumen Dental Group."),
        (PEH, 45, "Granite Peak Partners buys dental group Lumen Dental Group",
         LONG_HTML.format(d="The private equity firm adds a 40-office dental group in Colorado and Utah.")),
        (HD, 44, "Lumen Dental Group sold to Granite Peak Partners", ""),
    ],
    [
        (BPD, 9, "Vireo Pharma to buy Calder Therapeutics for $3.2B", "The deal adds a late-stage oncology drug."),
    ],
    # --- banking ----------------------------------------------------------------------------------
    [
        (PRN, 38, "Copperline Bancorp and First Prairie Bank Announce Merger Agreement", "OMAHA -- The combined bank will have $14 billion in assets."),
        (BD, 37, "Copperline Bancorp, First Prairie Bank to merge in $1.1B deal", ""),
    ],
    # --- energy (rumor, then announcement) ---------------------------------------------------------
    [
        (SA, 58, "Halcyon Energy in talks to acquire Redstone Midstream", ""),
        (UD, 30, "Halcyon Energy agrees to buy Redstone Midstream for $5.6 billion", ""),
    ],
    # --- industrials (completed) --------------------------------------------------------------------
    [
        (FT, 66, "Atlas Industrial to acquire Meridian Steel for $2.1bn", ""),
        (SCD, 6, "Atlas Industrial completes acquisition of Meridian Steel", ""),
    ],
    # --- fintech, insurance, consumer -------------------------------------------------------------
    [(PD, 13, "Tallyhook acquires payments startup Coinwell", "")],
    [(PEH, 24, "Kestrel Equity acquires HVAC services provider Summit Air Systems", None)],   # content:encoded only
    [(WM, 39, "Blue Heron Capital Takes Minority Stake In Oakmont Family Office | WealthManagement.com", "")],
    [(IJ, 25, "Harbor Mutual to acquire Pinewood Insurance Agency", "")],
    [(RD, 3, "Maple & Main to acquire Thistle Home in $640M deal", "")],
    # --- not deals: every one of these must be dropped ------------------------------------------------
    [
        (AH, 12, "Wirehouse Team Managing $2.1 Billion Breaks Away to Join Harborview Wealth Partners", "Should never be stored: gated source."),
        (IN, 8, "$2.1bn wirehouse team breaks away to join Harborview Wealth Partners", "The team cited technology and independence as reasons for the move."),
    ],
    [(IN, 33, "Coldstream hires former Kestrel Advisors CIO to lead investments", "Coldstream Wealth Management said the hire deepens its investment committee.")],
    [(WM, 34, "Pugh Capital Management Expands Fixed Income Team", "The Seattle firm adds two portfolio managers.")],
    [(WM, 64, "Coldstream Wealth Management Opens Portland Office", "The office is the firm's fifth in the Pacific Northwest.")],
    [(IN, 43, "SEC charges Ohio adviser in $3M cherry-picking scheme", "The SEC said the adviser allocated profitable trades to his own accounts.")],
    [(WM, 13, "SEC Proposes Revamp of Custody Rule for Crypto Assets", "Advisors would face new requirements for holding digital assets.")],
    [(FP, 32, "Interval funds see record inflows as advisors chase private credit", "Interval fund assets topped $100 billion for the first time.")],
    [(IN, 6, "Fed holds rates steady as advisors brace for volatility", "Policymakers signaled one more cut this year.")],
    [(RB, 2, "What the next generation of RIA founders wants from custodians", "")],
    [(RB, 44, "RIA M&A slows in the third quarter, DeVoe says", "")],
    [(WM, 20, "Why RIA Deals Keep Getting Bigger", "Valuations climbed again this year.")],
    [(PRN, 16, "SHAREHOLDER ALERT: Quinn & Hale Reminds Investors of Class Action Against Vireo Pharma", "")],
    [(PRN, 14, "Le groupe Exemple acquiert la Société Fictive pour renforcer son offre en Europe", "")],
    [(PRN, 500, "Old Merger Release From Last Spring: Acme Corp to Acquire Beta Corp", "Long ago.")],  # > 14 days old
    [(SA, 4, "Is Brightpath Analytics a buy after the Northwind deal?", "")],
    [(SA, 5, "Vanguard Group Inc. Raises Stake in Northwind Software", "")],
    [(FT, 12, "Global markets slide as bond yields climb", "")],
    [(PEH, 19, "PE fundraising slows in the third quarter", "")],
    [(TC, 17, "Lumio raises $30M Series B to build AI agents", "")],
    [(BD, 21, "Fed proposes changes to bank capital rules", "")],
    [(PD, 23, "Card issuers brace for new fee rules", "")],
    [(IJ, 29, "Hurricane season losses come in below forecasts", "")],
    [(RN, 31, "Catastrophe bond issuance hits a record in the third quarter", "")],
    [(BPD, 35, "FDA approves Calder Therapeutics drug for rare disease", "")],
    [(FH, 36, "Hospitals warn of staffing shortages this winter", "")],
    [(FB, 39, "Biotech seed funding slows as investors grow cautious", "")],
    [(FPH, 41, "Vireo Pharma lays off 300 in restructuring", "")],
    [(RD, 42, "Holiday sales forecast calls for modest growth", "")],
    [(UD, 47, "Grid operators plan for record winter demand", "")],
    [(SCD, 48, "Freight rates rise ahead of the holidays", "")],
    [(HD, 50, "Insurers expand coverage for telehealth visits", "")],
]

# Every source's items, in feed order (newest first)
by_source: dict[str, list[tuple[float, str, str]]] = {}
for story in STORIES:
    for src, hours, title, desc in story:
        by_source.setdefault(src, []).append((hours, title, desc))
for v in by_source.values():
    v.sort(key=lambda x: x[0])


def slug(title: str) -> str:
    s = "".join(c.lower() if c.isalnum() else "-" for c in title.split("|")[0])
    return "-".join(p for p in s.split("-") if p)[:80]


def rss(channel: str, link: str, items: list[str]) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<!-- {NOTE} -->\n"
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        f"<channel><title>{escape(channel)}</title><link>{link}</link><description>{NOTE}</description>\n"
        + "\n".join(items)
        + "\n</channel></rss>\n"
    )


def rss_item(title, link, date_str, desc=None, content=None, extra=""):
    parts = [f"<item><title>{escape(title)}</title><link>{escape(link)}</link><guid>{escape(link)}</guid><pubDate>{date_str}</pubDate>"]
    if desc is not None:
        parts.append(f"<description><![CDATA[{desc}]]></description>")
    if content is not None:
        parts.append(f"<content:encoded><![CDATA[{content}]]></content:encoded>")
    parts.append(extra + "</item>")
    return "".join(parts)


def dt(hours: float) -> datetime:
    return T0 - timedelta(hours=hours)


def rfc(hours: float, offset_hours: int = 0) -> str:
    tz = timezone(timedelta(hours=offset_hours))
    return format_datetime(dt(hours).astimezone(tz))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    routes: dict[str, dict] = {}
    full_text = "<p>FULL ARTICLE TEXT MUST NEVER BE STORED. " + "Paragraph. " * 200 + "</p>"

    def add(url, file=None, status=200, content_type="application/xml", headers=None, body=None):
        r = {"status": status, "content_type": content_type}
        if file:
            r["file"] = file
        if body is not None:
            r["body"] = body
        if headers:
            r["headers"] = headers
        routes[url] = r

    def write(name, text):
        (OUT / name).write_text(text, encoding="utf-8")
        return name

    allow_all = "User-agent: *\nDisallow: /admin/\n"

    # WealthManagement.com — configured RSS, -0400 offsets
    items = [rss_item(t, f"https://www.wealthmanagement.com/industry/{slug(t)}", rfc(h, -4), d) for h, t, d in by_source[WM]]
    add("https://www.wealthmanagement.com/rss.xml", write("wealthmanagement.xml", rss("WealthManagement.com", "https://www.wealthmanagement.com", items)),
        headers={"ETag": '"wm-v1"'})

    # InvestmentNews — homepage blocks bots (403) but /feed works
    add("https://www.investmentnews.com/robots.txt", body=allow_all, content_type="text/plain")
    add("https://www.investmentnews.com", status=403, body="Forbidden", content_type="text/html")
    items = [rss_item(t, f"https://www.investmentnews.com/{slug(t)}/{250000 + i}?fbclid=abc{i}", rfc(h, -4), d)
             for i, (h, t, d) in enumerate(by_source[IN])]
    add("https://www.investmentnews.com/feed", write("investmentnews.xml", rss("InvestmentNews", "https://www.investmentnews.com", items)))

    # RIABiz — no feed anywhere; listing page fallback
    add("https://riabiz.com/robots.txt", body=allow_all, content_type="text/plain")
    arts = []
    for i, (h, t, d) in enumerate(by_source[RB]):
        date = dt(h).astimezone(timezone(timedelta(hours=-7)))
        time_tag = f'<time datetime="{date.isoformat()}">{date.strftime("%B %d, %Y")}</time>' if i != 1 else ""
        arts.append(f'<article class="post"><h2><a href="/a/{7000 + i}/{slug(t)}">{escape(t)}</a></h2>{time_tag}<p>Teaser text is not collected from listings.</p></article>')
    add("https://riabiz.com", write("riabiz_home.html",
        f"<html><head><title>RIABiz</title></head><body><!-- {NOTE} --><nav><a href='/a/1/about-riabiz-and-our-team-here'>About RIABiz and our team here</a></nav>"
        + "".join(arts) + "<footer><a href='/tag/m-and-a'>M&amp;A tag page link text here</a></footer></body></html>"), content_type="text/html")
    add("https://riabiz.com/", file="riabiz_home.html", content_type="text/html")

    # Financial Planning — configured Atom feed, ISO-8601 with Z and +00:00
    entries = []
    for i, (h, t, d) in enumerate(by_source[FP]):
        stamp = dt(h).strftime("%Y-%m-%dT%H:%M:%SZ") if i % 2 == 0 else dt(h).isoformat()
        entries.append(f"<entry><title>{escape(t)}</title><link href=\"https://www.financial-planning.com/news/{slug(t)}\"/>"
                       f"<id>fp-{i}</id><updated>{stamp}</updated><summary type=\"html\">{escape(d)}</summary></entry>")
    add("https://www.financial-planning.com/feed?rss=true", write("financialplanning.xml",
        f'<?xml version="1.0" encoding="utf-8"?>\n<!-- {NOTE} -->\n<feed xmlns="http://www.w3.org/2005/Atom"><title>Financial Planning</title><id>fp</id><updated>{T0.isoformat()}</updated>\n'
        + "\n".join(entries) + "\n</feed>\n"))

    # AdvisorHub — configured RSS, gated: descriptions and content present but must not be stored
    items = [rss_item(t, f"https://www.advisorhub.com/{slug(t)}/", rfc(h, -4), d or "Teaser", full_text) for h, t, d in by_source[AH]]
    add("https://www.advisorhub.com/feed/", write("advisorhub.xml", rss("AdvisorHub", "https://www.advisorhub.com", items)))

    # Discovery test sites (not configured sources): <link rel="alternate"> on a homepage, and a common /rss path
    add("https://citywire.com/robots.txt", body=allow_all, content_type="text/plain")
    add("https://citywire.com/ria", write("citywire_home.html",
        '<html><head><title>Citywire RIA</title>'
        '<link rel="alternate" type="application/rss+xml" title="Comments" href="/ria/comments.rss">'
        '<link rel="alternate" type="application/rss+xml" title="Citywire RIA news" href="/ria/news.rss">'
        f"</head><body><!-- {NOTE} --></body></html>"), content_type="text/html")
    cw = [(30, "Harborview Wealth Partners buys $1.2bn Summit Ridge Advisors"), (22, "Crestline Wealth to buy Riverbend Financial"),
          (9, "Bear Mountain Capital makes minority investment in Willowbrook Wealth")]
    add("https://citywire.com/ria/news.rss", write("citywire.xml", rss("Citywire RIA", "https://citywire.com/ria",
        [rss_item(t, f"https://citywire.com/ria/news/{slug(t)}/a{2400000 + i}", rfc(h, 1), "") for i, (h, t) in enumerate(cw)])))
    add("https://www.fa-mag.com/robots.txt", body=allow_all, content_type="text/plain")
    add("https://www.fa-mag.com", write("famag_home.html", f"<html><head><title>FA Mag</title></head><body><!-- {NOTE} --></body></html>"), content_type="text/html")
    add("https://www.fa-mag.com/rss", write("famag.xml", rss("Financial Advisor Magazine", "https://www.fa-mag.com",
        [rss_item("Northgate Advisors And Pinecrest Wealth Merge", "https://www.fa-mag.com/news/northgate-81000.html", rfc(60, -5), "")])))

    # Google News: robots.txt disallows the search feeds (the real file does, 2026-10-17)
    add("https://news.google.com/robots.txt", body="User-agent: *\nDisallow: /rss/search\nAllow: /rss/articles\n", content_type="text/plain")

    # Deal sources (configured RSS). PR Newswire is a wire (robots-checked); the others are plain feeds.
    add("https://www.prnewswire.com/robots.txt", body=allow_all, content_type="text/plain")
    feeds = {
        PRN: ("https://www.prnewswire.com/rss/financial-services-latest-news/acquisitions-mergers-and-takeovers-list.rss",
              "prnewswire.xml", "https://www.prnewswire.com/news-releases/{slug}-30{i:04d}.html", -4),
        SA: ("https://seekingalpha.com/tag/m-a.xml", "seekingalpha.xml", "https://seekingalpha.com/news/{i}-{slug}", -4),
        FT: ("https://www.ft.com/companies?format=rss", "ft.xml", "https://www.ft.com/content/{i:08d}-{slug}", 0),
        PEH: ("https://www.pehub.com/feed/", "pehub.xml", "https://www.pehub.com/{slug}/", -4),
        TC: ("https://techcrunch.com/tag/mergers-and-acquisitions/feed/", "techcrunch.xml", "https://techcrunch.com/2026/09/{slug}/", -7),
        BD: ("https://www.bankingdive.com/feeds/news/", "bankingdive.xml", "https://www.bankingdive.com/news/{slug}/{i}/", -4),
        PD: ("https://www.paymentsdive.com/feeds/news/", "paymentsdive.xml", "https://www.paymentsdive.com/news/{slug}/{i}/", -4),
        IJ: ("https://www.insurancejournal.com/rss/news/", "insurancejournal.xml", "https://www.insurancejournal.com/news/{slug}.htm", -5),
        RN: ("https://www.reinsurancene.ws/feed/", "reinsurancenews.xml", "https://www.reinsurancene.ws/{slug}/", 0),
        BPD: ("https://www.biopharmadive.com/feeds/news/", "biopharmadive.xml", "https://www.biopharmadive.com/news/{slug}/{i}/", -4),
        HD: ("https://www.healthcaredive.com/feeds/news/", "healthcaredive.xml", "https://www.healthcaredive.com/news/{slug}/{i}/", -4),
        FH: ("https://www.fiercehealthcare.com/rss/xml", "fiercehealthcare.xml", "https://www.fiercehealthcare.com/{slug}", -4),
        FB: ("https://www.fiercebiotech.com/rss/xml", "fiercebiotech.xml", "https://www.fiercebiotech.com/{slug}", -4),
        FPH: ("https://www.fiercepharma.com/rss/xml", "fiercepharma.xml", "https://www.fiercepharma.com/{slug}", -4),
        RD: ("https://www.retaildive.com/feeds/news/", "retaildive.xml", "https://www.retaildive.com/news/{slug}/{i}/", -4),
        UD: ("https://www.utilitydive.com/feeds/news/", "utilitydive.xml", "https://www.utilitydive.com/news/{slug}/{i}/", -4),
        SCD: ("https://www.supplychaindive.com/feeds/news/", "supplychaindive.xml", "https://www.supplychaindive.com/news/{slug}/{i}/", -4),
    }
    for src_name, (feed, fname, link, tz) in feeds.items():
        items = [rss_item(t, link.format(slug=slug(t), i=700000 + i), rfc(h, tz), d or None,
                          full_text if src_name == PEH else None)   # PE Hub ships full articles: never stored
                 for i, (h, t, d) in enumerate(by_source.get(src_name, []))]
        add(feed, write(fname, rss(src_name, feed, items)))

    # SEC Investment Adviser Information Reports — synthetic monthly file (fictional firms, fake CRDs 9990xx)
    import csv
    import io
    import zipfile

    sec_page = "https://www.sec.gov/data-research/sec-markets-data/information-about-registered-investment-advisers-exempt-reporting-advisers"
    base = "/files/investment/data/information-about-registered-investment-advisers-exempt-reporting-advisers"
    add(sec_page, write("sec_ia_page.html",
        f"<html><body><!-- {NOTE} --><h1>Information About Registered Investment Advisers</h1>"
        f'<a href="{base}/ia090126.zip">September 2026</a> <a href="{base}/era090126.zip">ERA September 2026</a>'
        f'<a href="{base}/ia080126.zip">August 2026</a></body></html>'), content_type="text/html")
    firms = [
        # legal name, primary business name, city, state, regulatory AUM
        ("HARBORVIEW WEALTH PARTNERS, LLC", "HARBORVIEW WEALTH PARTNERS", "SEATTLE", "WA", 9_800_000_000),
        ("SUMMIT RIDGE ADVISORS LLC", "SUMMIT RIDGE ADVISORS", "DENVER", "CO", 1_200_000_000),
        ("CEDAR LANE PRIVATE WEALTH LLC", "CEDAR LANE PRIVATE WEALTH", "CHARLOTTE", "NC", 850_000_000),
        ("MERIDIAN CAPITAL PARTNERS LLC", "MERIDIAN CAPITAL PARTNERS", "PORTLAND", "OR", 6_100_000_000),
        ("OAKMONT FAMILY OFFICE LLC", "OAKMONT FAMILY OFFICE", "BELLEVUE", "WA", 2_300_000_000),
        ("NORTHGATE ADVISORS LLC", "NORTHGATE ADVISORS", "CHICAGO", "IL", 2_500_000_000),
        ("PINECREST WEALTH LLC", "PINECREST WEALTH", "CHICAGO", "IL", 2_000_000_000),
        ("LAKESHORE FINANCIAL GROUP, INC.", "LAKESHORE FINANCIAL GROUP", "MILWAUKEE", "WI", 640_000_000),
        ("ATLAS WEALTH MANAGEMENT LLC", "ATLAS WEALTH MANAGEMENT", "MINNEAPOLIS", "MN", 12_000_000_000),
        ("BIRCHWOOD ROW ADVISORY LLC", "BIRCHWOOD ROW ADVISORY", "MINNEAPOLIS", "MN", 300_000_000),
        ("CRESTLINE WEALTH LLC", "CRESTLINE WEALTH", "DALLAS", "TX", 7_000_000_000),
        ("RIVERBEND FINANCIAL LLC", "RIVERBEND FINANCIAL", "AUSTIN", "TX", 900_000_000),
        ("ASPEN GROVE ADVISORS LLC", "ASPEN GROVE ADVISORS", "BOULDER", "CO", 1_000_000_000),
        ("WILLOWBROOK WEALTH LLC", "WILLOWBROOK WEALTH", "SPOKANE", "WA", 1_100_000_000),
        ("SEQUOIA POINT WEALTH LLC", "SEQUOIA POINT WEALTH", "SAN JOSE", "CA", 2_800_000_000),
        ("BLUEWATER PRIVATE WEALTH LLC", "BLUEWATER PRIVATE WEALTH", "TAMPA", "FL", 3_000_000_000),
        ("KESTREL ADVISORS LLC", "KESTREL ADVISORS", "PORTLAND", "OR", 4_000_000_000),
        ("TIDEWATER FAMILY OFFICE LLC", "TIDEWATER FAMILY OFFICE", "NEW YORK", "NY", 500_000_000),
        # distractors for the precision guards
        ("SUMMIT WEALTH GROUP LLC", "SUMMIT WEALTH GROUP", "BOISE", "ID", 400_000_000),
        ("SUMMIT WEALTH PARTNERS LLC", "SUMMIT WEALTH PARTNERS", "OMAHA", "NE", 250_000_000),
        ("MERCER CAPITAL ADVISORS LLC", "MERCER CAPITAL ADVISORS", "MEMPHIS", "TN", 700_000_000),
        ("FOCUS ADVISORY LLC", "FOCUS ADVISORY", "RENO", "NV", 90_000_000),
    ]
    # Metro areas for the RIA map demo: (city, state, ZIP, lat, lon, weight). Approximate centroids; synthetic data.
    metros = [
        ("NEW YORK", "NY", "10022", 40.759, -73.968, 70), ("BOSTON", "MA", "02110", 42.357, -71.053, 26),
        ("CHICAGO", "IL", "60606", 41.882, -87.637, 30), ("SAN FRANCISCO", "CA", "94111", 37.799, -122.399, 28),
        ("LOS ANGELES", "CA", "90067", 34.058, -118.414, 26), ("DALLAS", "TX", "75201", 32.790, -96.804, 18),
        ("HOUSTON", "TX", "77002", 29.757, -95.365, 16), ("AUSTIN", "TX", "78701", 30.271, -97.744, 10),
        ("DENVER", "CO", "80202", 39.752, -104.999, 14), ("SEATTLE", "WA", "98101", 47.611, -122.337, 16),
        ("PORTLAND", "OR", "97204", 45.518, -122.676, 9), ("BELLEVUE", "WA", "98004", 47.618, -122.205, 6),
        ("SPOKANE", "WA", "99201", 47.663, -117.433, 3), ("BOISE", "ID", "83702", 43.632, -116.204, 4),
        ("SALT LAKE CITY", "UT", "84111", 40.757, -111.884, 6), ("PHOENIX", "AZ", "85004", 33.451, -112.069, 9),
        ("SCOTTSDALE", "AZ", "85251", 33.494, -111.921, 7), ("LAS VEGAS", "NV", "89101", 36.172, -115.122, 4),
        ("RENO", "NV", "89501", 39.526, -119.812, 2), ("SAN DIEGO", "CA", "92101", 32.719, -117.163, 10),
        ("SAN JOSE", "CA", "95113", 37.333, -121.889, 8), ("BOULDER", "CO", "80302", 40.017, -105.283, 5),
        ("MINNEAPOLIS", "MN", "55402", 44.976, -93.271, 12), ("MILWAUKEE", "WI", "53202", 43.043, -87.899, 6),
        ("ST. LOUIS", "MO", "63102", 38.627, -90.188, 8), ("KANSAS CITY", "MO", "64105", 39.102, -94.589, 7),
        ("OVERLAND PARK", "KS", "66210", 38.926, -94.705, 5), ("OMAHA", "NE", "68102", 41.262, -95.935, 5),
        ("DES MOINES", "IA", "50309", 41.587, -93.627, 3), ("DETROIT", "MI", "48226", 42.331, -83.047, 6),
        ("CLEVELAND", "OH", "44114", 41.507, -81.684, 7), ("COLUMBUS", "OH", "43215", 39.963, -83.005, 6),
        ("CINCINNATI", "OH", "45202", 39.104, -84.510, 6), ("INDIANAPOLIS", "IN", "46204", 39.771, -86.157, 6),
        ("NASHVILLE", "TN", "37219", 36.166, -86.784, 8), ("MEMPHIS", "TN", "38103", 35.150, -90.052, 4),
        ("ATLANTA", "GA", "30309", 33.799, -84.386, 16), ("CHARLOTTE", "NC", "28202", 35.228, -80.843, 11),
        ("RALEIGH", "NC", "27601", 35.774, -78.637, 6), ("RICHMOND", "VA", "23219", 37.540, -77.435, 6),
        ("WASHINGTON", "DC", "20006", 38.898, -77.040, 12), ("BALTIMORE", "MD", "21202", 39.296, -76.608, 7),
        ("PHILADELPHIA", "PA", "19103", 39.953, -75.173, 14), ("PITTSBURGH", "PA", "15222", 40.444, -79.996, 7),
        ("STAMFORD", "CT", "06901", 41.053, -73.537, 14), ("GREENWICH", "CT", "06830", 41.040, -73.626, 12),
        ("PRINCETON", "NJ", "08540", 40.357, -74.667, 6), ("MIAMI", "FL", "33131", 25.767, -80.190, 14),
        ("TAMPA", "FL", "33602", 27.951, -82.459, 8), ("NAPLES", "FL", "34102", 26.141, -81.795, 7),
        ("ORLANDO", "FL", "32801", 28.541, -81.379, 5), ("NEW ORLEANS", "LA", "70130", 29.950, -90.071, 4),
        ("OKLAHOMA CITY", "OK", "73102", 35.468, -97.516, 4), ("ALBUQUERQUE", "NM", "87102", 35.084, -106.650, 2),
        ("PORTLAND", "ME", "04101", 43.661, -70.255, 3), ("BURLINGTON", "VT", "05401", 44.476, -73.212, 2),
        ("ANCHORAGE", "AK", "99501", 61.217, -149.890, 2), ("HONOLULU", "HI", "96813", 21.309, -157.858, 3),
        ("CHARLESTON", "SC", "29401", 32.779, -79.931, 4), ("LOUISVILLE", "KY", "40202", 38.253, -85.759, 4),
        ("BIRMINGHAM", "AL", "35203", 33.519, -86.810, 3), ("SANTA FE", "NM", "87501", 35.687, -105.938, 2),
        ("CHAPEL HILL", "NC", "27514", 35.913, -79.056, 2), ("JACKSON", "WY", "83001", 43.479, -110.762, 2),
    ]
    by_city = {(c, st): z for c, st, z, *_ in metros}
    import random

    rnd = random.Random(7)
    words_a = ["Alder", "Basalt", "Bramble", "Corvid", "Dovetail", "Elmstead", "Fernhill", "Gable", "Halyard", "Ironbark",
               "Juniper", "Kestle", "Larkspur", "Marlow", "Northfork", "Oakhurst", "Pennant", "Quarry", "Rookwood",
               "Saltmarsh", "Thornbury", "Upland", "Vesper", "Wrenfield", "Yarrow", "Zephyr", "Ashgrove", "Bellwick",
               "Copperfield", "Driftwood", "Emberly", "Foxglove", "Greystone", "Hollis", "Inkwell", "Jasperwood"]
    words_b = ["Hill", "Creek", "Point", "Ridge", "Bay", "Grove", "Field", "Crossing", "Hollow", "Landing", "Commons", "Row"]
    words_c = ["Wealth Advisors", "Capital Management", "Private Wealth", "Financial Partners", "Investment Counsel",
               "Asset Management", "Family Office", "Wealth Management", "Advisory Group", "Fund Management"]
    synthetic, used = [], set()
    for city, st, z, la, lo, weight in metros:
        for _ in range(weight):
            while True:
                name = f"{rnd.choice(words_a)} {rnd.choice(words_b)} {rnd.choice(words_c)}"
                if name not in used:
                    used.add(name)
                    break
            aum = int(10 ** rnd.uniform(7.3, 10.2)) if rnd.random() > 0.03 else int(10 ** rnd.uniform(10.5, 12.2))
            synthetic.append((name.upper() + ", LLC", name.upper(), city, st, aum))

    def profile_cols(i: int, business: str, aum: int) -> list[str]:
        r = random.Random(i)
        if "FUND" in business:
            mix = {"f": aum * 0.8, "g": aum * 0.2}
        elif "ASSET" in business or "COUNSEL" in business:
            mix = {"g": aum * 0.5, "h": aum * 0.2, "b": aum * 0.3}
        else:
            hnw = r.uniform(0.5, 0.9)
            mix = {"b": aum * hnw, "a": aum * (1 - hnw) * 0.7, "g": aum * (1 - hnw) * 0.3}
        accounts = max(1, int(aum / r.uniform(4e5, 3e6)))
        yn = lambda p: "Y" if r.random() < p else "N"  # noqa: E731
        individuals = "b" in mix
        return [business.lower().replace(" ", "").replace(",", "") + ".example", f"{r.randint(1,12):02d}/{r.randint(1,28):02d}/{r.randint(1996, 2025)}",
                f"{r.randint(1,9):02d}/{r.randint(1,28):02d}/2026", r.choice(["Limited Liability Company", "Corporation", "Limited Partnership"]),
                str(r.randint(3, 120)), str(r.randint(2, 60)), str(r.randint(20, 2000)), str(r.randint(0, 6)),
                f"{aum * r.uniform(0.85, 1.0):,.2f}", f"{accounts:,}",
                *[f"{mix.get(x, 0):,.2f}" if mix.get(x) else "" for x in "abcdefghijklmn"],
                yn(0.85 if individuals else 0.2), yn(0.95 if individuals else 0.1), "N", yn(0.9 if not individuals else 0.05),
                yn(0.5 if not individuals else 0.15), yn(0.3), yn(0.25), "N", "N", "N", yn(0.1), "N",
                "Y", yn(0.4), "N", yn(0.6), yn(0.1), yn(0.9 if not individuals else 0.05), "N",
                yn(0.08), yn(0.15), yn(0.12), yn(0.07)]

    zips = {"SEATTLE": "98101", "DENVER": "80202", "CHARLOTTE": "28202", "PORTLAND": "97204", "BELLEVUE": "98004",
            "CHICAGO": "60606", "MILWAUKEE": "53202", "MINNEAPOLIS": "55402", "DALLAS": "75201", "AUSTIN": "78701",
            "BOULDER": "80302", "SPOKANE": "99201", "SAN JOSE": "95113", "TAMPA": "33602", "NEW YORK": "10022",
            "BOISE": "83702", "OMAHA": "68102", "MEMPHIS": "38103", "RENO": "89501"}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["SEC#", "Organization CRD#", "SEC Region", "Legal Name", "Primary Business Name", "Main Office City",
                "Main Office State", "Main Office Country", "Main Office Postal Code", "5F(2)(c)",
                "Website Address", "SEC Status Effective Date", "Latest ADV Filing Date", "3A", "5A", "5B(1)", "5C(1)",
                "Total number of offices, other than your Principal Office and place of business", "5F(2)(a)", "5F(2)(f)",
                *[f"5D({x})(3)" for x in "abcdefghijklmn"], *[f"5G({i})" for i in range(1, 13)],
                *[f"5E({i})" for i in range(1, 8)], "6A(1)", "6A(6)", "5I(1)", "11"])
    for i, (legal, business, city, state, aum) in enumerate(firms):
        w.writerow([f"801-{99000 + i}", str(999001 + i), "SEC", legal, business, city, state, "United States",
                    zips.get(city, ""), f"{aum:,}", *profile_cols(i, business, aum)])
    for j, (legal, business, city, state, aum) in enumerate(synthetic):
        w.writerow([f"801-{90000 + j}", str(970001 + j), "SEC", legal, business, city, state, "United States",
                    by_city[(city, state)] + ("-1234" if j % 7 == 0 else ""), f"{aum:,}", *profile_cols(1000 + j, business, aum)])
    w.writerow(["801-98999", "998002", "SEC", "LONDON BRIDGE ADVISERS LTD", "LONDON BRIDGE ADVISERS", "LONDON", "", "United Kingdom",
                "", "2,000,000,000", *profile_cols(5000, "LONDON BRIDGE ADVISERS", 2_000_000_000)])   # not on the US map
    w.writerow(["802-99999", "998001", "SEC", "EXEMPT REPORTING FUND ADVISER LLC", "HARBORVIEW VENTURES", "SEATTLE", "WA", "United States"])
    zi = zipfile.ZipInfo("IA_FIRM_SEC_Feed_09_01_2026.csv", date_time=(2026, 9, 1, 0, 0, 0))
    zbuf = io.BytesIO()   # fixed timestamps: regenerating the fixtures gives byte-identical zips
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zi, buf.getvalue())
        zf.writestr(zipfile.ZipInfo("README.txt", date_time=(2026, 9, 1, 0, 0, 0)), NOTE + "\n")
    (OUT / "sec_ia090126.zip").write_bytes(zbuf.getvalue())
    routes[f"https://www.sec.gov{base}/ia090126.zip"] = {"status": 200, "content_type": "application/zip", "file": "sec_ia090126.zip"}

    # Census ZCTA gazetteer (synthetic subset: the demo metros' ZIPs)
    gaz = "GEOID\tALAND\tAWATER\tALAND_SQMI\tAWATER_SQMI\tINTPTLAT\tINTPTLONG\n" + "".join(
        f"{z}\t1000000\t0\t0.386\t0\t{la:.6f}\t{lo:.6f}\n" for _, _, z, la, lo, _ in sorted({m[2]: m for m in metros}.values()))
    gbuf = io.BytesIO()
    with zipfile.ZipFile(gbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo("2024_Gaz_zcta_national.txt", date_time=(2024, 1, 1, 0, 0, 0)), gaz)
    (OUT / "zcta_gazetteer.zip").write_bytes(gbuf.getvalue())
    add("https://www2.census.gov/robots.txt", body=allow_all, content_type="text/plain")
    routes["https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip"] = {
        "status": 200, "content_type": "application/zip", "file": "zcta_gazetteer.zip"}

    # FINRA — robots.txt disallows the news section → failed with a robots reason
    add("https://www.finra.org/robots.txt", body="User-agent: *\nDisallow: /media-center/\n", content_type="text/plain")

    (OUT / "routes.yaml").write_text(
        f"# {NOTE}. Generated by scripts/make_fixtures.py — URL → saved response.\n"
        + yaml.safe_dump({"routes": routes}, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(routes)} routes to {OUT}")


if __name__ == "__main__":
    main()
