# Manual steps

Everything below is done in a web browser, apart from one optional command in step 2. Each feature that
needs a secret is optional. Without the secret, the refresh still runs and the run log shows a notice saying
what was skipped.

| Step | Needed for | Required? |
|---|---|---|
| 1. Make the repository private | keeping the database and code out of public view | recommended |
| 2. Add a Claude secret | AI-written digest and weekly paragraph | optional |
| 3. Add the watchlist email secrets | email when new stories match your firms | optional |
| 4. Check the Vercel and Actions settings | already done in phase 1; verify only | check |

---

## 1. Make the repository private (recommended)

The `live` branch holds the private state (the SQLite database with publisher teasers, digest archive, firm
match report). The public site never contains it, but anyone who can see the repo can read it. A private
repo keeps it private. It also avoids GitHub's rule that pauses scheduled workflows in public repos after
60 days without activity.

1. Open https://github.com/SantiMiguel11/Wealth-Wire.
2. Click **Settings** (top bar of the repo).
3. On the **General** page, scroll to the bottom: **Danger Zone**.
4. Click **Change repository visibility** → **Change to private**, then confirm.

**Vercel keeps working with a private repo.** The Vercel GitHub app you installed in phase 1 already has
access to this repo and doesn't care about visibility. To double-check:
1. Go to https://github.com/settings/installations.
2. Click **Configure** next to **Vercel**.
3. Under **Repository access**, make sure either **All repositories** is chosen, or **Wealth-Wire** is in the
   list.

GitHub Actions minutes: private repos on the free plan include 2,000 minutes a month. A refresh takes about
2–4 minutes, and there are about 80 runs a month, so usage is roughly 250 minutes.

---

## 2. Claude secret for the AI digest (optional)

Without this, the Digest tab shows the ranked story list with no summaries, which is the fallback. Add **one**
of the two secrets below. If both are set, the OAuth token is used.

### Option A (preferred): `CLAUDE_CODE_OAUTH_TOKEN`, uses your Claude Pro/Max subscription

1. On any computer with Claude Code installed, run this once in a terminal:
   `claude setup-token`
   Log in when the browser opens. The terminal prints a long token starting with `sk-ant-oat…`. Copy it.
2. Open https://github.com/SantiMiguel11/Wealth-Wire/settings/secrets/actions
   (**Settings** → **Secrets and variables** → **Actions**).
3. Click **New repository secret**.
4. **Name:** `CLAUDE_CODE_OAUTH_TOKEN`. **Secret:** paste the token. Click **Add secret**.

### Option B: `ANTHROPIC_API_KEY`, pay per use through the API

1. Open https://console.anthropic.com/settings/keys, then click **Create Key**, name it `wealth-wire`, and copy
   the key (`sk-ant-api…`).
2. Make sure the account has credit: **Settings** → **Billing**. Each digest uses a small amount.
3. Add it as described in steps 2–4 of Option A, with the name `ANTHROPIC_API_KEY`.

**Check it worked:**
1. Open **Actions** → **Refresh site** → **Run workflow** (branch `main`) → **Run workflow**.
2. When the run finishes, open it. The summary should show `digest: ok: N stories`, and the Digest tab on the
   site should show "Today in wealth management".
3. If it says `fallback: …`, the reason is right there. The site still works either way.

---

## 3. Watchlist email (optional)

After each refresh you get one email listing new stories about firms on your watchlist. No matches means no
email. The email is only sent when **all three** secrets below are set.

1. **Create a Resend account.** Sign up at https://resend.com with the email address you want alerts sent to.
   Resend's shared sender (`onboarding@resend.dev`) can only deliver to your account's own address, so use
   that address.
2. **Create an API key.** In Resend, go to **API Keys** → **Create API Key**, name it `wealth-wire`, choose
   **Sending access**, and click **Add**. Copy the key (`re_…`).
3. **Export your watchlist.** On the Wealth Wire site, add your firms in the Watchlist panel, click
   **Export JSON**, and open the downloaded `wealth-wire-watchlist.json` in a text editor. Copy all of it.
4. **Add three repository secrets.** Use the same page as step 2 above: **New repository secret** for each.

   | Name | Value |
   |---|---|
   | `RESEND_API_KEY` | the `re_…` key |
   | `ALERT_EMAIL` | your Resend account email (several allowed, comma-separated, if you verify a domain) |
   | `WATCHLIST_JSON` | the whole contents of the exported file |

5. **Optional repository variables.** On the same page, open the **Variables** tab → **New repository
   variable**.
   - `SITE_URL`: your Vercel URL, e.g. `https://wealth-wire.vercel.app`, adds a link to the email.
   - `ALERT_FROM`: e.g. `Wealth Wire <alerts@yourdomain.com>`. Set this only after verifying a domain in
     Resend (**Domains** → **Add Domain**).

The watchlist secret is only read in memory during the email step. It is never written to a file, and it
never appears in logs (a test enforces this). The watchlist on the website is separate: it lives only in
your browser. If you change it on the site, export it again and update `WATCHLIST_JSON`.

---

## 4. Check the Vercel and GitHub settings (already done in phase 1)

**Vercel:** open your project at https://vercel.com/dashboard, then **Settings** → **Git** (or
**Environments** → **Production**).
- **Production Branch** must be `live`.
- **Root Directory** is empty (the repo root). `vercel.json` on `live` sets the output folder to `site` and
  adds the `noindex` header and the `/firm/...` page route.
- **Framework Preset:** Other. No build command.

**GitHub Actions permissions:** open https://github.com/SantiMiguel11/Wealth-Wire/settings/actions.
- Under **Workflow permissions**, select **Read and write permissions** and click **Save**. The refresh needs
  this to push to `live`, and it has been working, so it is already set.

---

## Everyday use

- **Refresh now:** **Actions** → **Refresh site** → **Run workflow**.
- **Schedule:** weekdays about 6:00, 12:00 and 17:00 Pacific, and weekends about 8:00. During winter
  (standard time) each run is an hour earlier; see the comments in `.github/workflows/refresh-site.yml`.
- **See what happened:** open any run. The summary lists each source's status, the digest status and the
  firm-matching score.
- **Nothing to maintain.** The SEC adviser file is checked monthly and downloaded only when a new one is out.
