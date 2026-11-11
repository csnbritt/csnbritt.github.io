# csnbritt.github.io

Personal site built with [Jekyll](https://jekyllrb.com/), served by GitHub Pages.

## Local development

```bash
jekyll serve
# → http://localhost:4000
```

## Writing a post

Add a file to `_posts/` named `YYYY-MM-DD-title.md` with front matter:

```markdown
---
layout: post
title: "My post title"
---

Content in Markdown.
```

The 5 most recent posts appear automatically on the home page; all posts are
listed at `/blog/`.

## Music page

Albums are listed in `_data/albums.yml` (`title`, `artist`, optional `cover`,
`link`, `note`) and rendered as a cover grid at `/music/`.

To fetch cover art automatically (iTunes API → Cover Art Archive fallback):

```bash
python3 scripts/fetch_covers.py           # fetch missing covers, update albums.yml
python3 scripts/fetch_covers.py --all     # re-fetch everything
python3 scripts/fetch_covers.py --dry-run # show what would be fetched
```

## Personalizing

Edit `_config.yml` — name, tagline, and links (email, github, scholar, etc.)
are all configured there. Empty values are hidden automatically.

## Deploying

Push to `main`. GitHub Pages builds and serves the site automatically —
no CI needed.