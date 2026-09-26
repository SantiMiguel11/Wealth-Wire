import pytest

from wealthwire.categorize import Categorizer


@pytest.fixture(scope="module")
def cat(request):
    return Categorizer()


@pytest.mark.parametrize(
    "title, expected",
    [
        # --- People Moves: advisor/team moves are NOT M&A ---
        ("Wirehouse Team With $2.1B Breaks Away to Harborview Wealth Partners", "People Moves"),
        ("Alder Street team with $400M joins Bluewater Private Wealth", "People Moves"),
        ("Merrill advisor managing $300M moves to Raymond James", "People Moves"),
        ("Coldstream hires former Kestrel Advisors CIO to lead investments", "People Moves"),
        ("UBS advisor departs for independent RIA", "People Moves"),
        ("$1.5B team jumps to LPL from Morgan Stanley", "People Moves"),
        ("Rockefeller hires $2B team from JPMorgan", "People Moves"),
        ("Pinecrest Wealth names Dana Ortiz CEO ahead of Northgate merger", "People Moves"),
        ("Breakaway team joins Harborview after firm's acquisition spree", "People Moves"),
        ("Former Goldman Sachs Advisors Launch Tidewater Family Office", "People Moves"),
        ("Kestrel Advisors appoints new chief investment officer", "People Moves"),
        # --- M&A ---
        ("Harborview Wealth Partners buys $1.2bn Summit Ridge Advisors", "M&A"),
        ("Harborview Wealth Partners to Acquire Summit Ridge Advisors", "M&A"),
        ("Atlas Wealth Management acquires Brookfield Row Advisory", "M&A"),
        ("Cedar Lane Private Wealth sells to Meridian Capital Partners", "M&A"),
        ("Northgate Advisors and Pinecrest Wealth Merge to Form $4.5B Firm", "M&A"),
        ("Blue Heron Capital Takes Minority Stake In Oakmont Family Office", "M&A"),
        ("Bear Mountain Capital makes minority investment in Willowbrook Wealth", "M&A"),
        ("Lakeshore Financial Group agrees to be acquired by Atlas Wealth Management", "M&A"),
        ("Sequoia Point Wealth completes recapitalization with Granite Peak Partners", "M&A"),
        ("Two Texas RIAs combine in deal creating $3bn firm", "M&A"),
        ("Meridian Capital Partners adds $850M Cedar Lane Private Wealth", "M&A"),
        ("RIA M&A hits record in third quarter", "M&A"),
        # --- others ---
        ("SEC Charges Ohio Investment Adviser With Cherry-Picking Scheme", "Regulation"),
        ("FINRA fines broker-dealer $1.5 million over supervision lapses", "Regulation"),
        ("SEC proposes changes to custody rule for crypto assets", "Regulation"),
        ("Ledgerline launches AI meeting-notes assistant for RIAs", "Wealthtech"),
        ("The Latest In Financial #AdvisorTech (September 2026)", "Wealthtech"),
        ("Goldman Sachs Asset Management Launches Two Active ETFs", "Products & Funds"),
        ("Interval funds see record inflows as advisors chase private credit", "Products & Funds"),
        ("Fed Holds Rates Steady, Signals One More Cut", "Markets"),
        ("S&P 500 Notches Record As Tech Rally Broadens", "Markets"),
        ("Coldstream Wealth Management Opens Portland Office", "Other"),
        ("Weekend Reading For Financial Planners (September 20-21)", "Other"),
    ],
)
def test_categories(cat, title, expected):
    assert cat.categorize(title) == expected


def test_description_used_only_as_fallback(cat):
    assert cat.categorize("A quiet week", "The SEC proposed a new rule on custody.") == "Regulation"
    # title decides when it matches; M&A title-only rules ignore description verbs
    assert cat.categorize("Fed holds rates", "Firm acquires rival") == "Markets"
    assert cat.categorize("Weekend musings", "Mariner acquires rival") == "Other"


def test_word_boundaries(cat):
    assert cat.categorize("Secondary thoughts on fees") == "Other"  # 'SEC' inside a word
    assert cat.categorize("The rulers of wealth") == "Other"
