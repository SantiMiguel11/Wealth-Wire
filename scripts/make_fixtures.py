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

# (source, hours_before_T0, title, description)
S = "SEC Press Releases"
TA, WM, CW, FA, IN, RB, FP, AH, KI = (
    "ThinkAdvisor", "WealthManagement.com", "Citywire RIA", "Financial Advisor Magazine",
    "InvestmentNews", "RIABiz", "Financial Planning", "AdvisorHub", "Kitces",
)

STORIES: list[list[tuple[str, float, str, str]]] = [
    # --- M&A ---------------------------------------------------------------------------------------
    [
        (CW, 30, "Harborview Wealth Partners buys $1.2bn Summit Ridge Advisors", "The Denver-based consolidator adds a $1.2bn RIA with 14 advisors, its fifth deal this year."),
        (TA, 28, "Harborview Wealth Partners Acquires $1.2B Summit Ridge Advisors | ThinkAdvisor", "Summit Ridge Advisors, which manages $1.2 billion, will keep its brand and leadership team."),
        (WM, 26, "Harborview Wealth Partners to Acquire Summit Ridge Advisors, a $1.2 Billion RIA", "The deal is expected to close in the fourth quarter."),
        (RB, 20, "Harborview Wealth Partners scoops up Summit Ridge Advisors as its RIA buying spree continues", ""),
    ],
    [
        (CW, 52, "Cedar Lane Private Wealth sells to Meridian Capital Partners", "Cedar Lane, an $850M RIA in Charlotte, becomes Meridian's first Southeast office."),
        (IN, 49, "Meridian Capital Partners adds $850M Cedar Lane Private Wealth", "Meridian Capital Partners continues its push into the Carolinas."),
    ],
    [
        (FA, 40, "Blue Heron Capital Takes Minority Stake In Oakmont Family Office", "The private equity firm's investment values Oakmont at an undisclosed sum."),
        (FP, 37, "Blue Heron Capital takes minority stake in Oakmont Family Office", "Oakmont oversees $2.3 billion for 60 ultra-high-net-worth families."),
    ],
    [
        (TA, 62, "Northgate Advisors and Pinecrest Wealth Merge to Form $4.5B Firm", "The combined firm will operate under the Northgate name."),
        (WM, 60, "Northgate Advisors and Pinecrest Wealth merge in $4.5 billion combination", "Both founders will serve as co-CEOs of the combined RIA."),
    ],
    [
        (IN, 18, "Lakeshore Financial Group agrees to be acquired by Atlas Wealth Management", "Lakeshore, with $640 million in assets, is Atlas's second Midwest deal."),
    ],
    [
        (IN, 70, "Atlas Wealth Management acquires Brookfield Row Advisory", "Atlas adds a $300M practice in Minneapolis."),
    ],
    [
        (CW, 14, "Two Texas RIAs combine in deal creating $3bn firm", "The firms, based in Austin and Dallas, did not disclose terms."),
    ],
    [
        (RB, 44, "Serial acquirer strikes again with $600M buy in Arizona", ""),
    ],
    [
        (TA, 22, "PE-Backed Crestline Wealth to Buy Riverbend Financial and Aspen Grove Advisors", "The two deals add a combined $1.9B in client assets."),
        (FA, 21, "Crestline Wealth To Buy Riverbend Financial, Aspen Grove Advisors", "Crestline is backed by private equity firm Granite Peak Partners."),
    ],
    [
        (CW, 9, "Bear Mountain Capital makes minority investment in Willowbrook Wealth", "Willowbrook, a $1.1bn multifamily office, will use the capital to fund succession."),
        (RB, 7, "Willowbrook Wealth lands minority investment from Bear Mountain Capital", ""),
    ],
    [
        (FP, 56, "Sequoia Point Wealth completes recapitalization with Granite Peak Partners", "The $2.8B firm says the deal gives next-generation advisors a path to equity."),
    ],
    # --- People Moves ------------------------------------------------------------------------------
    [
        (AH, 12, "Wirehouse Team Managing $2.1 Billion Breaks Away to Join Harborview Wealth Partners", "Should never be stored: gated source."),
        (TA, 10, "Wirehouse Team With $2.1B Breaks Away to Harborview Wealth Partners | ThinkAdvisor", "The four-advisor team served ultra-high-net-worth clients in Chicago."),
        (CW, 8, "$2.1bn wirehouse team breaks away to join Harborview Wealth Partners", "The team cited technology and independence as reasons for the move."),
    ],
    [
        (CW, 33, "Coldstream hires former Kestrel Advisors CIO to lead investments", "Coldstream Wealth Management said the hire deepens its investment committee."),
    ],
    [
        (FP, 26, "Pinecrest Wealth names Dana Ortiz CEO ahead of Northgate merger", "Ortiz previously served as president of the firm."),
    ],
    [
        (AH, 5, "Alder Street Securities Team With $400 Million Joins Bluewater Private Wealth", ""),
        (IN, 4, "Alder Street team with $400M joins Bluewater Private Wealth", "The father-son team moves after 22 years at the broker-dealer."),
    ],
    [
        (FA, 58, "Former Goldman Sachs Advisors Launch Tidewater Family Office", "The founders previously worked in Goldman's private wealth unit in New York."),
    ],
    [
        (WM, 34, "Pugh Capital Management Expands Fixed Income Team", "The Seattle firm adds two portfolio managers."),
    ],
    # --- Regulation --------------------------------------------------------------------------------
    [
        (S, 46, "SEC Charges Ohio Investment Adviser With Cherry-Picking Scheme", "The Securities and Exchange Commission today charged an Ohio-based investment adviser with a $3 million cherry-picking scheme."),
        (IN, 43, "SEC charges Ohio adviser in $3M cherry-picking scheme", "The SEC said the adviser allocated profitable trades to his own accounts."),
        (TA, 41, "SEC Charges Ohio Advisor Over Cherry-Picking Scheme | ThinkAdvisor", "Regulators say losing trades went to clients."),
    ],
    [
        (S, 30, "SEC Charges New Jersey Adviser With Misappropriating Client Funds", "The adviser allegedly diverted $1.4 million from elderly clients."),
    ],
    [
        (IN, 29, "FINRA fines broker-dealer $1.5 million over supervision lapses", "The self-regulator said the firm failed to review 1.2 million alerts."),
        (FP, 27, "FINRA fines broker-dealer $1.5M for supervision failures", "The firm neither admitted nor denied the findings."),
    ],
    [
        (FP, 15, "SEC proposes changes to custody rule for crypto assets", "The proposal would narrow the definition of a qualified custodian."),
        (WM, 13, "SEC Proposes Revamp of Custody Rule for Crypto Assets", "Advisors would face new requirements for holding digital assets."),
        (TA, 11, "SEC Proposes Custody Rule Changes for Crypto | ThinkAdvisor", "Comment period runs 60 days."),
    ],
    [
        (S, 3, "SEC Announces Enforcement Results for Fiscal Year 2026", "The agency filed 612 enforcement actions in fiscal 2026."),
    ],
    [
        (KI, 36, "How Advisors Can Navigate The DOL's Revised Fiduciary Rule", LONG_HTML.format(d="A practical guide to the Department of Labor's retirement advice rule and what changes for rollover recommendations.")),
    ],
    # --- Wealthtech --------------------------------------------------------------------------------
    [
        (CW, 24, "Ledgerline launches AI meeting-notes assistant for RIAs", "The wealthtech startup says the tool integrates with major CRMs."),
        (TA, 23, "Ledgerline Launches AI Meeting-Notes Assistant for RIAs | ThinkAdvisor", "Pricing starts at $95 per advisor per month."),
        (WM, 22, "Ledgerline Rolls Out AI Meeting-Notes Assistant for RIAs", "The launch follows a $40 million funding round."),
    ],
    [
        (FA, 50, "Arbor Clearing Rolls Out New Advisor Portal", "The custodian's portal adds digital account opening."),
    ],
    [
        (KI, 60, "The Latest In Financial #AdvisorTech (September 2026)", None),
    ],
    # --- Products & Funds --------------------------------------------------------------------------
    [
        (WM, 20, "Goldman Sachs Asset Management Launches Two Active ETFs", "The funds target short-duration income."),
        (FA, 19, "Goldman Sachs Asset Management Launches Pair Of Active ETFs", "Both ETFs list on NYSE Arca."),
        (TA, 17, "Goldman Sachs Asset Management Launches 2 Active ETFs | ThinkAdvisor", "Expense ratios are 0.35% and 0.45%."),
    ],
    [
        (FP, 32, "Interval funds see record inflows as advisors chase private credit", "Interval fund assets topped $100 billion for the first time."),
    ],
    [
        (IN, 38, "Vantage Street unveils model portfolios for tax-aware investors", "The models use direct indexing sleeves."),
    ],
    # --- Markets -----------------------------------------------------------------------------------
    [
        (IN, 6, "Fed holds rates steady as advisors brace for volatility", "Policymakers signaled one more cut this year."),
        (FA, 5.5, "Fed Holds Rates Steady, Signals One More Cut", "Markets rallied on the decision."),
        (WM, 5, "Fed Holds Rates Steady; What Advisors Should Tell Clients", "Strategists weigh in on bonds and equities."),
    ],
    [
        (FA, 16, "S&P 500 Notches Record As Tech Rally Broadens", "Equities rose for a fifth straight session."),
    ],
    # --- Other -------------------------------------------------------------------------------------
    [
        (KI, 45, "Weekend Reading For Financial Planners (September 20-21)", LONG_HTML.format(d="This week's edition kicks off with news from the industry.")),
    ],
    [
        (IN, 66, "InvestmentNews announces 2026 Excellence Awards winners", "Winners will be honored in New York in November."),
    ],
    [
        (WM, 64, "Coldstream Wealth Management Opens Portland Office", "The office is the firm's fifth in the Pacific Northwest."),
    ],
    [
        (RB, 2, "What the next generation of RIA founders wants from custodians", ""),
    ],
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

    # ThinkAdvisor — configured RSS, UTC "GMT" dates, utm params
    items = [rss_item(t, f"https://www.thinkadvisor.com/2026/09/{dt(h).day}/{slug(t)}/?utm_source=rss&utm_medium=feed", rfc(h), d)
             for h, t, d in by_source[TA]]
    add("https://www.thinkadvisor.com/feed/", write("thinkadvisor.xml", rss("ThinkAdvisor", "https://www.thinkadvisor.com", items)))

    # WealthManagement.com — configured RSS, -0400 offsets
    items = [rss_item(t, f"https://www.wealthmanagement.com/industry/{slug(t)}", rfc(h, -4), d) for h, t, d in by_source[WM]]
    add("https://www.wealthmanagement.com/rss.xml", write("wealthmanagement.xml", rss("WealthManagement.com", "https://www.wealthmanagement.com", items)),
        headers={"ETag": '"wm-v1"'})

    # Citywire — autodiscovery via <link rel="alternate">, +0100 offsets
    add("https://citywire.com/robots.txt", body=allow_all, content_type="text/plain")
    add("https://citywire.com/ria", write("citywire_home.html",
        '<html><head><title>Citywire RIA</title>'
        '<link rel="alternate" type="application/rss+xml" title="Comments" href="/ria/comments.rss">'
        '<link rel="alternate" type="application/rss+xml" title="Citywire RIA news" href="/ria/news.rss">'
        f"</head><body><!-- {NOTE} --></body></html>"), content_type="text/html")
    items = [rss_item(t, f"https://citywire.com/ria/news/{slug(t)}/a{2400000 + i}#comments", rfc(h, 1), d)
             for i, (h, t, d) in enumerate(by_source[CW])]
    add("https://citywire.com/ria/news.rss", write("citywire.xml", rss("Citywire RIA", "https://citywire.com/ria", items)))

    # Financial Advisor Magazine — no alternate link; /feed 404s; /rss works (common path)
    add("https://www.fa-mag.com/robots.txt", body=allow_all, content_type="text/plain")
    add("https://www.fa-mag.com", write("famag_home.html", f"<html><head><title>FA Mag</title></head><body><!-- {NOTE} --></body></html>"), content_type="text/html")
    items = [rss_item(t, f"https://www.fa-mag.com/news/{slug(t)}-{81000 + i}.html", rfc(h, -5), d)
             for i, (h, t, d) in enumerate(by_source[FA])]
    add("https://www.fa-mag.com/rss", write("famag.xml", rss("Financial Advisor Magazine", "https://www.fa-mag.com", items)))

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

    # Kitces — long HTML descriptions + content:encoded; one item with content:encoded only
    items = [rss_item(t, f"https://www.kitces.com/blog/{slug(t)}/", rfc(h, -4), d, full_text) for h, t, d in by_source[KI]]
    add("https://www.kitces.com/feed/", write("kitces.xml", rss("Nerd's Eye View | Kitces.com", "https://www.kitces.com", items)))

    # SEC — configured RSS with ETag (conditional GET), EDT offsets
    items = [rss_item(t, f"https://www.sec.gov/newsroom/press-releases/2026-{120 + i}", rfc(h, -4), d) for i, (h, t, d) in enumerate(by_source[S])]
    add("https://www.sec.gov/news/pressreleases.rss", write("sec.xml", rss("SEC Press Releases", "https://www.sec.gov", items)),
        headers={"ETag": '"sec-v1"', "Last-Modified": rfc(3)})

    # FINRA — robots.txt disallows the news section → failed with a robots reason
    add("https://www.finra.org/robots.txt", body="User-agent: *\nDisallow: /media-center/\n", content_type="text/plain")

    (OUT / "routes.yaml").write_text(
        f"# {NOTE}. Generated by scripts/make_fixtures.py — URL → saved response.\n"
        + yaml.safe_dump({"routes": routes}, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(routes)} routes to {OUT}")


if __name__ == "__main__":
    main()
