# VRAMLab temporary navigation review

Temporary static rendering of the authorized nav-2026-10-07 site changes.
It contains the existing public reports and assets only. The production site,
DNS, analytics collectors and weekly automation are not changed by this repo.
All review HTML is noindex/nofollow, points canonical links to production, and
omits the existing analytics beacon. Review routes use the repository prefix.
This preview should be disabled and archived after the requested browser QA.
Do not treat its page views or metadata as a production SEO experiment.

## Native browser search failure fixtures

Normal /search/ keeps the production search bundle and normal index unchanged.
Only preview query modes ?__qa_failure=http-error, invalid-json, network or
timeout enable a one-request fixture. HTTP uses an actual intentionally absent
hosted index (404); JSON/network/pending-timeout responses are controlled. Retry
then loads the real hosted index. The browser renders the actual page and bundle;
this is not a claim of a real production outage. The helper is temporary and is
never copied to the production source or deployment.
