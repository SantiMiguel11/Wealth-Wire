---
description: Write today's Fiduciary Wire digest locally, using the same instructions and validation as the refresh workflow
allowed-tools: Bash(python -m fiduciarywire digest-input), Bash(python -m fiduciarywire digest-finalize), Read(./prompts/digest.md), Read(./_work/**), Write(./_work/digest_output.json), Write(./_work/weekly_output.json)
---

The scheduled refresh on GitHub normally writes the digest (see `.github/workflows/refresh-site.yml`). This
command does the same thing on your machine against your local database. Do not fetch any web page or
open any article link.

1. Run exactly `python -m fiduciarywire digest-input`. It writes `_work/digest_input.json`, plus
   `_work/weekly_input.json` on Fridays.
2. Read `prompts/digest.md` and follow it exactly. It names the input and output files and the writing rules.
3. Run exactly `python -m fiduciarywire digest-finalize`. It validates what you wrote. If validation fails, it
   prints the reasons. Fix the output file once, then run finalize again.
4. Reply with one line: the digest status that finalize printed.
