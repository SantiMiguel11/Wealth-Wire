"""Deals only: decide whether a headline announces an actual M&A deal, and describe it.

A headline counts as a deal when it parses as a deal event with at least one named party ("Acme to acquire
Beta", "Beta agrees to be acquired by Acme", "Acme completes acquisition of Beta", "Acme in talks to buy Beta",
"Beta rejects bid from Acme"). Rejected:
- commentary about deals ("RIA M&A drops 17% in Q3", "Why deals keep getting bigger");
- a fund's 13F position change ("Vanguard Group Raises Stake in Apple");
- buybacks, financings, IPOs, funding rounds, licensing pacts, purchases of goods ("buy up to 1.6 GW of …");
- advisor and executive moves, which use the same verbs in RIA trade press ("adds $1.1B team");
- headlines that aren't in English (wires syndicate translations).

Every source goes through this; nothing else is stored (DECISIONS D2).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .extract import money_spans
from .firms import GEO, is_word

COMMENTARY = re.compile(
    r"\?\s*$|^(?:why|how|what|when|where|who|which|should|could|would|can|is|are|does|do|inside|opinion|"
    r"commentary|analysis|podcast|webinar|video|watch|listen|q&a|ask|this week|the weekly|weekly)\b|\binterview\b|"
    r"\b(?:m&a|deals?|mergers?|acquisitions?|consolidation|dealmaking|deal-making|transactions?)\s+"
    r"(?:activity|volume|volumes|market|markets|slowdown|slows|slowed|cools|cooled|surges?|surged|rebounds?|drops?|dropped|"
    r"falls?|fell|rises?|rose|climbs?|trends?|outlook|report|record|records|pace|boom|frenzy|wave|landscape|environment|"
    r"playbook|tips|lessons|strateg(?:y|ies)|valuations?|multiples|count|counts|data|index|tracker|roundup|recap|"
    r"advice|mistakes|checklist|guide|predictions?|forecasts?|survey|study|panel|summit|conference|insights|"
    r"pipeline|appetite|momentum|drought|freeze|thaw|risks?|hurdles?|headwinds|tailwinds|rules|scrutiny|debate|"
    r"signals?|spree|streak|refugees)\b|"
    r"\b(?:q[1-4]|first[- ]quarter|second[- ]quarter|third[- ]quarter|fourth[- ]quarter|first[- ]half|second[- ]half|"
    r"year[- ]to[- ]date|ytd|annual|monthly|quarterly)\b.{0,40}\b(?:m&a|deals|transactions)\b|"
    r"\b(?:m&a|deals)\b.{0,40}\b(?:q[1-4]|this year|last year|so far)\b|"
    r"\b\d+\s+deals\b|\bdeals? (?:&|and) moves\b|\bfundraising tracker\b|\bep\.? ?\d+\b|\bepisode\b|#\w+",
    re.I,
)
NOT_A_DEAL = re.compile(
    r"\bnew (?:stake|position)\b|\b(?:position|positions|holdings?)\s+in\b|\bshares\s+(?:of|in)\b|\b\d[\d,]*\s+shares\b|"
    r"\b(?:raises|boosts|lifts|increases|grows|trims|cuts|lowers|reduces|decreases)\s+(?:its\s+|their\s+)?"
    r"(?:stake|position|holdings?)\b|"
    r"\bbuy\s?backs?\b|\bbuys? back\b|\b(?:share|stock) repurchases?\b|\brepurchase program\b|"
    r"\brefinanc\w*|\bcredit facility\b|\bdebt (?:sale|offering)\b|\bnotes offering\b|\bipo\b|\binitial public offering\b|"
    r"\bgoes public\b|\bgo public\b|\bspac\b|\bseries [a-e]\b|\bseed (?:round|funding)\b|\bfunding round\b|"
    r"\b(?:raises|raised|secures|lands|nabs|banks|closes)\s+\$[\d.,]+\s*(?:[mb]n?|million|billion)?\s+(?:in\s+)?(?:funding|round|series|seed|financing|capital|fund)\b|"
    r"\b(?:buy|strong buy|outperform|overweight)\s+rating\b|\bstocks? to buy\b|\bbuy the dip\b|\bbuy now,? pay later\b|"
    r"\bbuy-side\b|\b(?:customer|client|user|talent|data|land)\s+acquisitions?\b|"
    r"\bacquires?\s+(?:new\s+)?(?:customers|clients|users|talent|rights to|license|licenses|patent|patents|land|"
    r"aircraft|vessels?|ships?|equipment|tickets)\b|"
    r"\b\d[\d.,]*\s?(?:gw|mw|mwh|gwh|units|tons|tonnes|barrels|acres|homes|apartments|beds)\b|"
    r"\b(?:denies|denied|deny|rumou?rs? denied)\b|\b(?:pact|licens\w+|co-develop\w*|collaboration (?:deal|agreement)|partnership deal)\b|"
    r"\bclass action\b|\bshareholder (?:alert|action)\b|\binvestors? (?:who|have|with)\b|\binvestigat\w+\b",
    re.I,
)
# Advisor and executive moves use the same verbs as deals in RIA trade press ("adds $1.1B team", "lands duo").
PEOPLE = re.compile(r"\b(?:team|teams|duo|trio|quartet|joins|joined|hires|hired|hiring|breaks away|breakaway|recruits|recruited|"
                    r"poaches|departs|defects|names|named|appoints|appointed|promotes|promoted|taps|ceo|president|chief|"
                    r"advisors? who|brokers? who|bankers?|executive|exec|leader|head of|co-ceo)\b", re.I)
STRONG = re.compile(r"\b(?:acquir\w*|merg\w*|buys?|bought|to buy|purchas\w*|takeover|take-private|buyout|stake|"
                    r"recapitaliz\w*|divest\w*|sells?|sold|to sell|sale of|carve)\b|"
                    r"\bwith (?:\$\S+ )?(?-i:[A-Z])[\w&'’ -]+ deal\b|\b(?:double|triple)[- ]deal\b", re.I)
_FOREIGN = re.compile(r"\b(?:la|le|les|des|du|et|pour|avec|sus|una|unen|para|con|und|der|die|das|mit|für|il|della|per|"
                      r"een|het|voor|ve|bir|için|się|oraz|dla|completa|acquiert|adquiere|übernimmt|acquisisce|sobre)\b", re.I)

TERMINATED = re.compile(r"\b(?:terminat\w+|calls? off|called off|abandon\w*|scraps?|scrapped|walks? away|collaps\w+|"
                        r"blocks?|blocked|sues to block|ends? (?:merger|deal|talks)|pulls? out of|withdraws? (?:its )?(?:offer|bid)|"
                        r"rejects?|rejected|rebuffs?|spurns?)\b", re.I)
RUMORED = re.compile(r"\b(?:in talks|talks to|in advanced talks|nears? (?:a )?deal|close to (?:a )?deal|near(?:ing)? (?:a )?deal|"
                     r"explor\w+ (?:a )?(?:sale|merger|deal)|consider\w* (?:a )?(?:sale|merger|bid)|weighs?|eyes|eyeing|"
                     r"said to|reportedly|sources say|report says|people familiar|mulls?|in discussions?)\b", re.I)
BID = re.compile(r"\b(?:bids?|offers? for|offer to (?:buy|acquire)|proposal to (?:buy|acquire)|hostile|unsolicited|"
                 r"tender offer|raises (?:its )?(?:offer|bid)|sweetens?)\b", re.I)
COMPLETED = re.compile(r"\b(?:complet\w+|closes|closed|closing of|finaliz\w+|has acquired|consummat\w+|now part of|"
                       r"officially joins|wraps up)\b", re.I)

_A, _B = r"(?P<a>.+?)", r"(?P<b>.+?)"
_MONEY_W = r"(?:\$[\d.,]+\s*(?:[a-zA-Z]{1,8})?\+?\s+)"
PATTERNS: list[tuple[str, re.Pattern]] = [(t, re.compile(p, re.I)) for t, p in [
    # target is the subject
    ("acquisition", rf"^{_B}\s+(?:is\s+|are\s+)?(?:reportedly\s+)?(?:agrees? to be|to be|will be|has been|was|is being|being|in (?:advanced |exclusive )?talks to be|"
                    rf"nears? deal to be|set to be)\s+(?:acquired|bought|taken private|purchased|sold(?=\s+to\b))(?:\s+(?:by|to)\s+(?P<a>.+?))?(?:\s+(?:for|in|at|from)\b.*|,.*|\s+[-–—].*)?$"),
    ("acquisition", rf"^{_B}\s+(?:acquired|bought|taken private|purchased)\s+by\s+(?P<a>.+)$"),
    ("acquisition", rf"^{_B}\s+(?:enters? into|signs?|announces?|reaches?)\s+(?:an?\s+|the\s+)?(?:definitive\s+|merger\s+)*(?:agreement|deal)\s+to\s+be\s+(?:acquired|bought)\s+by\s+(?P<a>.+)$"),
    ("acquisition", rf"^{_B}\s+(?:rejects?|rejected|rebuffs?|spurns?)\s+(?:an?\s+|the\s+|its\s+)?(?:[\w$.,-]+\s+){{0,3}}(?:bid|offer|proposal|approach)\s+from\s+(?P<a>.+)$"),
    ("acquisition", rf"^{_B}\s+agrees? to (?:an?\s+)?{_MONEY_W}?(?:acquisition|buyout|takeover|sale|take-private)(?:\s+deal)?\b.*$"),
    ("acquisition", rf"^{_B}\s+(?:sells|sold|to sell|agrees to sell)\s+(?:itself\s+|firm\s+|business\s+|company\s+)?to\s+(?P<a>.+)$"),
    # seller sells a unit to a buyer
    ("acquisition", rf"^(?P<s>.+?)\s+(?:to sell|sells|sold|agrees to sell|divests|to divest|offloads|unloads|completes (?:the )?sale of|closes (?:the )?sale of)\s+{_B}\s+to\s+(?P<a>.+)$"),
    ("acquisition", rf"^{_A}\s+(?:to buy|buys|acquires|to acquire)\s+{_B}\s+from\s+(?P<s>.+)$"),
    # stakes and recapitalizations
    ("stake", rf"^{_A}\s+(?:takes?|to take|acquires?|buys?|to buy|agrees to buy|makes?)\s+(?:an?\s+)?(?:\d+%\s+)?(?:minority|majority|strategic|significant|controlling|non-controlling|growth)?\s*(?:equity\s+)?(?:stake|investment)\s+in\s+{_B}$"),
    ("stake", rf"^{_B}\s+(?:sells?|to sell|agrees to sell)\s+(?:an?\s+)?(?:\d+%\s+)?(?:minority|majority|significant|strategic|non-controlling)?\s*stake\s+to\s+(?P<a>.+)$"),
    ("stake", rf"^{_B}\s+(?:lands|gets|receives|secures|accepts|announces)\s+(?:an?\s+)?(?:minority|majority|strategic|significant|growth)\s*(?:equity\s+)?(?:stake|investment)\s+from\s+(?P<a>.+)$"),
    ("recapitalization", rf"^{_B}\s+(?:completes\s+|announces\s+|closes\s+|finalizes\s+)?(?:an?\s+)?(?:recapitalization|recap)\s+(?:with|led by|backed by)\s+(?P<a>.+)$"),
    ("recapitalization", rf"^{_A}\s+(?:leads|backs|completes)\s+(?:an?\s+)?recapitalization of\s+{_B}$"),
    # mergers
    ("merger", rf"^{_A}\s*(?:,|\s+and|\s+&)\s+{_B}\s+(?:to merge|agree to merge|merge|announce (?:a\s+)?(?:\w+\s+)?merger|complete (?:\w+\s+)?merger|"
               rf"sign merger agreement|to combine|combine|in merger talks|merger|combination)\b.*$"),
    ("merger", rf"^{_A}\s+(?:merges|to merge|will merge|agrees? to merge|combines|to combine|completes merger|announces merger)\s+with\s+{_B}$"),
    ("merger", rf"^{_A}\s+(?:enters? into|signs?|announces?|reaches?)\s+(?:an?\s+|the\s+)?(?:definitive\s+)?(?:merger agreement|agreement to merge)\s+with\s+{_B}$"),
    # agreements, completions, bids, talks
    ("acquisition", rf"^{_A}\s+(?:enters? into|signs?|announces?|reaches?|strikes?|inks?|in|cuts?)\s+(?:an?\s+|the\s+)?(?:definitive\s+|merger\s+|binding\s+)*"
                    rf"(?:agreement|deal)\s+to\s+(?:acquire|buy|purchase|carve out|take private)\s+{_B}$"),
    ("acquisition", rf"^{_A}\s+(?:completes?|closes?|finalizes?|announces?|consummates?|makes?|pens|inks?|strikes?|unveils|agrees to|seals?)\s+"
                    rf"(?:its\s+|the\s+|an?\s+)?(?:completion of (?:the |its )?|closing of (?:the |its )?)?{_MONEY_W}?(?:[\w’'-]+\s+){{0,4}}?"
                    rf"(?:acquisition|purchase|takeover|buyout|take-private)\s+(?:of|with|for|to (?:buy|acquire))\s+{_B}$"),
    ("acquisition", rf"^{_A}\s+(?:announces?|makes?|pens|inks?|strikes?|agrees to|seals?|cuts?|lands?)\s+(?:its\s+|the\s+|an?\s+)?{_MONEY_W}?(?:[\w’'-]+\s+){{0,3}}?"
                    rf"deal\s+(?:to date\s+)?(?:with|to (?:buy|acquire))\s+(?P<b>{_MONEY_W}?.+?)$"),
    ("acquisition", rf"^{_A}\s+(?:completes?|closes?|finalizes?|wins approval for|gets approval for|seals?)\s+(?:its\s+|the\s+|an?\s+)?"
                    rf"(?:historic\s+|long-awaited\s+|blockbuster\s+|landmark\s+|pending\s+|proposed\s+|planned\s+)?{_MONEY_W}?"
                    rf"(?P<b>(?-i:[A-Z])[\w.&'’-]*(?:\s+(?-i:[A-Z])[\w.&'’-]*){{0,4}})\s+(?:merger|acquisition|takeover|deal|buyout|purchase)\b.*$"),
    ("acquisition", rf"^{_A}\s+(?:enters|expands into|moves into|grows in|adds)\s+.{{0,40}}?\bwith\s+{_MONEY_W}?{_B}\s+(?:acquisition|deal|purchase|buy)\b.*$"),
    ("acquisition", rf"^{_A}\s+(?:enters|expands into|moves into|grows in|adds)\s+.{{0,40}}?\bwith\s+{_MONEY_W}{_B}$"),
    ("acquisition", rf"^(?:.*?\b(?:on|over|for|of|in|about|approves?|clears?|probes?|backs?)\s+)?(?P<a>(?-i:[A-Z])[\w.&-]*(?:\s+(?-i:[A-Z])[\w.&-]*){{0,4}})['’]s\s+"
                    rf"{_MONEY_W}?(?:proposed\s+|planned\s+|pending\s+)?(?!(?:Billion|Million|Trillion|Bn|Mn)\b)(?P<b>(?-i:[A-Z])[\w.&'-]*(?:\s+(?-i:[A-Z])[\w.&'-]*){{0,4}})\s+(?:deal|acquisition|takeover|merger|buyout|purchase)\b.*$"),
    ("acquisition", rf"^{_A}\s+(?:is\s+|are\s+)?(?:reportedly\s+)?(?:in (?:advanced |exclusive |early )?talks|nears? (?:a )?deal|near(?:ing)? (?:a )?deal|close to (?:a )?deal|in discussions)\s+"
                    rf"(?:to\s+)?(?:acquire|buy|for|with|over|merge with)\s+{_B}$"),
    ("acquisition", rf"^{_A}\s+(?:makes?|launches?|submits?|sweetens?|offers?|tables?)\s+(?:an?\s+|its\s+)?(?:[\w$.,-]+\s+){{0,3}}(?:bid|offer|proposal|tender offer)\s+(?:for|to acquire|to buy)\s+{_B}$"),
    ("acquisition", rf"^{_A}\s+raises\s+{_B}\s+(?:takeover\s+|buyout\s+)?(?:bid|offer)\b.*$"),
    ("acquisition", rf"^{_A}\s+(?:to carve out|carves out|strikes deal to carve out)\s+{_B}$"),
    ("acquisition", rf"^{_A}\s+(?:wins|gets|receives|secures|obtains)\s+(?:[\w-]+\s+){{0,3}}(?:approval|clearance|nod|green light)\s+(?:to|for)\s+(?:acquire|buy|purchase|take over|merge with)\s+{_B}$"),
    ("acquisition", rf"^{_A}\s+(?:confirms|says|said|announces)?\s*(?:it\s+)?(?:will|plans to|is set to|set to|has agreed to|agreed to|is buying|is acquiring|"
                    rf"will reportedly|is reportedly|reportedly)\s+(?:to\s+)?(?:acquire|buy|purchase|take over)\s+{_B}$"),
    ("acquisition", rf"^{_A}\s+(?:paid|pays|spends|spent|is spending|to pay|will pay|agrees to pay)\s+{_MONEY_W}(?:upfront\s+)?(?:for|to buy|to acquire)\s+{_B}$"),
    # RIA trade-press forms
    ("acquisition", rf"^(?P<a>(?-i:[A-Z])[\w.&'’-]*(?:\s+(?-i:[A-Z])[\w.&'’-]*){{0,5}})['’]s\s+(?:\d+(?:st|nd|rd|th)\s+|first\s+|second\s+|third\s+|latest\s+|largest\s+|newest\s+)?"
                    rf"(?:acquisition|deal|purchase)\s+(?:is\s+|of\s+|for\s+|:\s+)+{_B}$"),
    ("acquisition", rf"^(?:.*?\s)?(?P<a>(?-i:[A-Z])[\w.&'’-]*(?:\s+(?-i:[A-Z])[\w.&'’-]*){{0,3}})\s+(?:buy|purchase|acquisition|takeover|buyout)\s+of\s+{_B}$"),
    ("acquisition", rf"^{_A}\s+(?:adds|lands|completes|closes|announces|strikes|inks|notches)\s+.{{0,60}}?\b(?:double|triple|two-firm|three-firm|dual|multi-firm)[- ]deal\b.*$"),
    ("acquisition", rf"^{_A}\s+(?:adds|lands)\s+.{{0,60}}?\bdeal hat[- ]trick\b.*$"),
    ("acquisition", rf"^(?P<a>(?-i:[A-Z])[\w.&'’-]*(?:\s+(?-i:[A-Z])[\w.&'’-]*){{0,5}}?)\s+\w+s\s+(?:[\w$.,'’-]+\s+){{0,8}}?with\s+{_MONEY_W}?(?P<b>(?-i:[A-Z])[\w.&'’-]*(?:\s+(?-i:[A-Z])[\w.&'’-]*){{0,5}})\s+(?:acquisition|deal|purchase|buy|merger)\s*$"),
    # the plain verbs, last
    ("acquisition", rf"^{_A}\s+(?P<plain>agrees to acquire|agrees to buy|to acquire|to buy|acquires|acquired|buys|bought|snaps up|scoops up|purchases|to purchase|"
                    rf"swoops on|gobbles up|takes over|to take over|takes private|to take private|completes purchase of|closes on|"
                    rf"(?P<weak>adds|to add|lands|snags|nabs|grabs))\s+{_B}$"),
    ("acquisition", rf"^(?P<a>(?-i:[A-Z])[\w.&'’-]*(?:\s+(?-i:[A-Z])[\w.&'’-]*){{0,3}}(?:,|\s+and|\s+&)\s+(?-i:[A-Z])[\w.&'’-]*(?:\s+(?-i:[A-Z])[\w.&'’-]*){{0,3}})\s+"
                    rf"(?P<plain>buy|acquire|purchase)\s+{_B}$"),
]]

_WORD = r"(?:[A-Z0-9][\w.&'’+-]*|[a-z]+[A-Z][\w.&'’+-]*)"   # "Acme", "3M", "upGrad", "eBay"
_RUN = re.compile(rf"{_WORD}(?:\s+(?:{_WORD}|of|de|la|the|and|&|\+)(?=\s|$))*")
_CUT = re.compile(r"\s*(?:[,;:(]|\s[-–—]\s|—|–|\.\.\.)|\s+(?:in|to|for|as|after|amid|with|worth|valued|from|at|on|while|marking|"
                  r"its|that|which|who|following|despite|ahead|over|under|via|through|into|said|reportedly|report)\b|"
                  r"\s+(?:and|&)\s+(?=[A-Z][a-z]+s\b)", re.I)
# Descriptors that Title Case headlines capitalize ("Louisiana RIA Cullen", "IRA Platform Alto", "Tax Firm CohnReznick");
# other descriptors only count in lowercase, so "Bank of America" keeps its name.
TITLE_DESCRIPTOR = {"ria", "firm", "platform", "practice", "provider", "startup", "office", "consolidator", "aggregator", "biz"}
DESCRIPTOR = re.compile(r"^(?:supplier|provider|maker|startup|start-up|firm|company|developer|operator|platform|specialist|"
                        r"manufacturer|distributor|producer|retailer|chain|brand|lender|insurer|broker|brokerage|consultancy|"
                        r"agency|ria|practice|office|manager|owner|recycler|notetaker|rival|unit|business|biz|subsidiary|division|"
                        r"group|outfit|shop|player|vendor|carrier|consolidator|aggregator|adviser|advisor|bank|bancorp|"
                        r"services|solutions|holdings|partner|investor)$", re.I)
_SKIP_LEAD = {"aum", "the", "a", "an", "us", "u.s.", "uk", "u.k.", "eu", "former", "rival", "fellow"}
_PLACES = {"us", "u.s.", "uk", "u.k.", "america", "india", "china", "japan", "germany", "france", "canada", "europe", "brazil",
           "australia", "britain", "italy", "spain", "mexico", "korea", "singapore", "israel", "texas", "california", "florida",
           "new york", "ireland", "switzerland", "sweden", "netherlands", "dutch", "swiss", "chinese", "indian"}
_NOT_PARTY = {"no", "yes", "this", "that", "these", "those", "it", "they", "we", "he", "she", "here", "there", "report", "reports",
              "sources", "exclusive", "update", "breaking", "company", "firm", "deal", "deals", "acquisition", "merger", "rival",
              "ria", "rias", "family office", "practice", "team", "startup", "bank", "m&a"}
_GENERIC = {"ria", "rias", "firm", "firms", "team", "teams", "advisor", "advisors", "adviser", "advisers", "practice", "wealth",
            "manager", "managers", "business", "shop", "office", "family", "multifamily", "independent", "hybrid", "rival",
            "two", "three", "another", "stake", "minority", "majority", "undisclosed", "breakaway", "consolidator", "acquirer",
            "group", "partners", "company", "platform", "startup", "unit", "provider", "biz", "planning", "financial"}
_FIRMISH = re.compile(r"\$[\d.,]|\b(?:ria|rias|firm|practice|family office|advisors?|advisers?|partners|wealth|group|capital|"
                      r"management|financial|holdings|inc\.?|llc|corp\.?|company)\b", re.I)
_FIRM_NOUN = re.compile(r"\b(?:ria|rias|firm|practice|family office|advisors?|advisers?|partners|wealth|capital|management|"
                        r"financial|holdings|inc\.?|llc|corp\.?|company|group)\b", re.I)
_LEAD = re.compile(r"^(?:(?:exclusive|breaking|update|updated|report|reports|deal news|m&a|press release|ria moves|ria deals?|"
                   r"deal roundup|in brief|scoop|first on [\w ]+)\s*:\s*)+", re.I)
_PRICE = re.compile(r"(?:\bfor\b|\bin an?\b|\bvalued at\b|\bworth\b|\bvaluing\b|\bpriced at\b|\bdeal valued at\b|\bfor about\b|"
                    r"\bfor roughly\b|\bfor up to\b|\bpays?\b|\bpaid\b|\bspends?\b|\bspent\b|\binks?\b|\bstrikes?\b|\bagrees to an?\b|"
                    r"\bannounces?\b)\s*(?:about|roughly|nearly|around|up to|approximately|an?)?\s*$", re.I)
_PRICE_AFTER = re.compile(r"^\+?\s*(?:all-cash\s+|all-stock\s+|cash-and-stock\s+|cash\s+and\s+stock\s+|upfront\s+)?"
                          r"(?:deal|acquisition|takeover|buyout|merger|transaction|bid|offer|purchase|sale|tie-up|take-private|to buy|to acquire)\b", re.I)


@dataclass
class DealSignal:
    acquirer: str
    target: str
    deal_type: str             # acquisition | merger | stake | recapitalization
    stage: str                 # announced | completed | rumored | bid | terminated
    value_usd: float | None    # stated price / deal value (never a target's AUM)
    seller: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> str:
        return "high" if self.acquirer and self.target and not self.notes else "low"


def _clean(title: str) -> str:
    t = re.sub(r"\s+[|]\s+.*$", "", (title or "").strip())
    return _LEAD.sub("", t).strip().rstrip(".")


def _runs(text: str) -> list[str]:
    return [m.group(0).strip() for m in _RUN.finditer(text)]


def _name(text: str | None, first: bool, leading: bool = True) -> str:
    """A party name from a captured phrase. Acquirers: the phrase up to the first clause break. Targets: same, then
    the last proper-noun run after any descriptor ('Italian frozen foods group Rispo' → 'Rispo')."""
    if not text:
        return ""
    t = re.sub(r"^(?:\$[\d.,]+\s*(?:[a-zA-Z]{1,8})?\+?\s+)+", "", text.strip(" ,.;:'\"“”"))
    m = _CUT.search(t)
    if m:
        t = t[: m.start()]
    runs = _runs(t)
    if not runs:
        return ""
    # a subject phrase ends in its name ("US nutrition startup Berry Street"); an object after "by"/"to" starts
    # with it ("by Proofpoint signals more M&A")
    name = runs[-1] if leading else runs[0]
    words = name.split()
    # drop a descriptor run that heads the name ("Louisiana RIA Cullen Investment Group", "Self-Directed IRA Platform Alto")
    def descriptor(w: str) -> bool:
        w = w.strip(".,")
        return bool(DESCRIPTOR.match(w)) and (w.islower() or w.lower() in TITLE_DESCRIPTOR)
    for i in range(len(words) - 1, -1, -1):
        if descriptor(words[i]):
            if i == len(words) - 1:
                if not first or len(words) > 1 and words[i].lower() in TITLE_DESCRIPTOR:
                    return ""  # "Louisiana RIA", "Naples Practice", "OCIO Provider": a description, not a name
                continue
            words = words[i + 1:]
            break
    while words and (words[0].lower().strip(".,") in _SKIP_LEAD or re.search(r"-(?:backed|based)$", words[0].lower())
                     or re.sub(r"['’]s$", "", words[0]).lower() in _PLACES and re.search(r"['’]s$", words[0])):
        words = words[1:]  # "Thrive-backed Console", "India's Unacademy"
    if words and words[-1].lower().endswith("-based"):
        return ""  # "Cayman Islands-based family office": a place, not a name
    while words and words[-1].lower() in {"of", "de", "la", "the", "and", "&", "+"}:
        words.pop()
    name = re.sub(r"(?:'s|’s)$", "", " ".join(words)).strip(" ,.;:")
    low = name.lower()
    if not re.search(r"[A-Za-z]", name) or re.match(r"^\d+(?:\.\d+)?(?:/share)?$", name):
        return ""  # "$49.75/share"
    if not name or low in _NOT_PARTY or len(words) > 8:
        return ""
    if all(w.lower().strip(".,'’s") in _GENERIC or re.match(r"^\$", w) for w in words):
        return ""
    if low in GEO or low in _PLACES or (len(words) == 1 and not first and re.search(r"(?:ing|ed)$", low) and is_word(low)):
        return ""  # "Long Island", "Specializing"
    return name


def _ends_with_name(text: str) -> bool:
    """Acquirer phrases must end in the name ('US startup Berry Street' yes; 'No sooner does X … than it massively' no)."""
    t = text.strip(" ,.;:'\"“”")
    m = _CUT.search(t)
    t = t[: m.start()] if m else t
    runs = list(_RUN.finditer(t))
    return bool(runs) and runs[-1].end() >= len(t.rstrip(" .,’'")) - 1


def _value(title: str) -> float | None:
    for start, end, v in money_spans(title):
        if v < 1e6:
            continue
        before, after = title[max(0, start - 30): start], title[end: end + 30]
        if _PRICE.search(before) or _PRICE_AFTER.match(after):
            if re.match(r"^\s*(?:[\w.'’-]+\s+){0,3}?(?:ria|rias|firm|firms|practice|family office|wealth|advis\w*|aum|in aum|"
                        r"in assets|assets|business|team|trust business|multifamily office)\b", after, re.I):
                continue  # "$1B Louisiana RIA": that's the target's AUM
            return v
    return None


def _stage(title: str) -> str:
    if TERMINATED.search(title):
        return "terminated"
    if RUMORED.search(title):
        return "rumored"
    if BID.search(title):
        return "bid"
    if COMPLETED.search(title):
        return "completed"
    return "announced"


def _foreign(title: str) -> bool:
    return len(_FOREIGN.findall(title)) >= 2 or bool(re.search(r"[«»¿¡]", title))


def classify(title: str) -> DealSignal | None:
    """The deal a headline announces, or None when it isn't one."""
    raw = (title or "").strip()
    if not raw or _foreign(raw) or COMMENTARY.search(raw) or NOT_A_DEAL.search(raw):
        return None
    text = _clean(raw)
    if not text or COMMENTARY.search(text) or (PEOPLE.search(text) and not STRONG.search(text)):
        return None
    for deal_type, pat in PATTERNS:
        m = pat.match(text)
        if not m:
            continue
        g = m.groupdict()
        acq = _name(g.get("a"), True, leading=bool(g.get("a")) and m.start("a") == 0)
        tgt, seller = _name(g.get("b"), False), _name(g.get("s"), True)
        if g.get("a") and acq and m.start("a") == 0 and not _ends_with_name(g["a"]):
            acq = ""
        b_raw = g.get("b") or ""
        cut = _CUT.search(b_raw)
        b_head = b_raw[: cut.start()] if cut and cut.start() > 0 else b_raw
        money_firm = re.match(r"^\$[\d.,]+\s*\S*\s+(?:AUM\s+)?(?-i:[A-Z])(?!(?:Of|In|To|For)\b)", b_head, re.I)
        if g.get("weak") and (not ((tgt or money_firm) and (_FIRM_NOUN.search(b_head) or money_firm))
                              or re.search(r"\b(?:advis[eo]r|broker|banker|rep|planner|executive)s?\s*$", b_head, re.I)):
            return None  # "X adds Income Lab as member benefit", "X nabs $93M for …": not a deal without a firm target
        if g.get("plain") and not tgt and not (_FIRMISH.search(b_head) or any(DESCRIPTOR.match(w) for w in b_head.split())):
            return None  # "GSK … picks up steam", "Kraken parent eyes …": a verb, but nothing bought
        if not (acq or tgt):
            continue
        if acq and tgt and acq.lower() == tgt.lower():
            continue
        if not tgt and seller:  # "AT&T to sell Mexico wireless business to Televisa": the seller's unit
            unit = re.sub(r"^(?:its|their|the|a|an)\s+", "", b_head.strip(), flags=re.I)
            tgt = f"{seller}’s {unit}" if unit and len(unit.split()) <= 5 and not unit[0].isdigit() else seller
        notes = [] if acq and tgt else [("acquirer" if not acq else "target") + " not named in the headline"]
        return DealSignal(acquirer=acq, target=tgt, deal_type=deal_type, stage=_stage(raw), value_usd=_value(raw),
                          seller=seller, notes=notes)
    return None


def is_deal(title: str) -> bool:
    return classify(title) is not None
