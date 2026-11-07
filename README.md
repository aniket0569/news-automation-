# CLAT: Final Round — website package

A static site. No build step, no framework, no server. Upload the folder and it works.

```
index.html        the storefront (all styling inline)
thank-you.html    what a buyer sees after the free-download form
legal.html        terms, refunds, privacy  (gateways check this page)
404.html          not-found page
assets/           favicon + social preview image + logo SVGs
downloads/        the free PDFs that get delivered
netlify.toml      headers for Netlify
_headers          same headers for Cloudflare Pages
robots.txt        blocks /downloads from crawlers
sitemap.xml       edit the domain inside
```

---

## 1. Put it online (10 minutes)

**Netlify (easiest, and the form works out of the box)**
1. Go to app.netlify.com → *Add new site* → *Deploy manually*.
2. Drag this whole folder onto the page. You get a live URL like `random-name.netlify.app`.
3. *Domain settings* → add your own domain and follow the DNS instructions.

**Cloudflare Pages** — Workers & Pages → Create → Pages → *Upload assets* → drag the folder.
**GitHub Pages** — push the folder to a repo, Settings → Pages → deploy from the branch root.

---

## 2. Nothing to connect

There is no checkout on this site. Every paper downloads free, after the visitor
gives an email address. When you want to introduce paid papers later, the README
section you need is the `CONFIG` block at the bottom of `index.html` — it already
holds a `freeDownloads` map you can duplicate for a `payments` map.

## 3. How the free downloads work

Free items open a small dialog asking for an email and consent, then POST to the
form and hand over the file.

- **On Netlify:** nothing to configure. `formEndpoint` stays `""` and submissions
  appear under *Forms* in the Netlify dashboard. Add a notification email there
  so you hear about each one.
- **On any other host:** create a form at formspree.io (free tier is fine) and
  paste its URL into `formEndpoint`.
- A visitor who has already given an address downloads straight away — the
  address is remembered in their browser.

The five free files live in `downloads/`. Replace them with new editions and
keep the filenames, or update the paths in `CONFIG.freeDownloads`.

**This is lead capture, not DRM.** Anyone who reads the page source can find the
PDF path. That is normal for a small site: the gate collects addresses and the
goodwill of a fair price does the rest. If a file starts circulating, change its
filename and update `CONFIG`.

---

## 4. Adding a product

1. Copy an `<article class="card" ...>` block in the library section.
2. Give it a unique `data-id` (e.g. `mock-03`), the right `data-kind`
   (`mock` or `notes`) and `data-price` (`free` or `paid`).
3. Add the same id to `CONFIG.freeDownloads`, pointing at the PDF in `downloads/`.
4. Update the title, description and the meta line.

The filter chips pick up new cards automatically.

---

## 5. Before you tell anyone about it

- [ ] Replace `hello@clatfinalround.in` everywhere (index, legal, thank-you).
- [ ] Fill in the owner box at the bottom of `legal.html` — trading name, address,
      GSTIN when you have one, payment provider.
- [ ] Put your real domain into `sitemap.xml` and the `og:url` in `index.html`.
- [ ] Test a free download end to end, and check the address lands in Netlify Forms.
- [ ] Download all five PDFs from the live site and check each opens.
- [ ] Open the site on a phone. The library, the dialog and the footer should all work.

## 6. Notes

- Fonts load from Google Fonts; offline, the page falls back to Georgia and the
  system sans, which still reads correctly.
- Everything is one ink: black on paper. No images to load, so pages are fast.
- The site is not affiliated with the Consortium of NLUs — that line is in the
  footer and in `legal.html`. Keep it.
