# Blog assets — Landscape Problem Diagnosis

## Main article

- **[diagnostics-engine-neurosymbolic-ai.md](./diagnostics-engine-neurosymbolic-ai.md)** — full blog post

## Infographics (`assets/`)

| File | Description |
|------|-------------|
| [methodology-pipeline.svg](./assets/methodology-pipeline.svg) | Production systems → papers → dictionary → cards → normalize → fine-tune |
| [framework-hierarchy.svg](./assets/framework-hierarchy.svg) | Production system → observed stress → causal pathways (8 built) |
| [pathway-structure.svg](./assets/pathway-structure.svg) | Signals, confirmation policy, follow-up questions |

## To add later

- Triaging app confusion matrices (before / after automated fine-tuning)
- Screenshots of `/triaging`, `/review`, Commons Connect integration mockups

## Publishing notes

- SVGs render on GitHub and most static site generators. For WordPress or CMS paste, upload SVG or export PNG.
- **Cursor / VS Code markdown preview:** SVG is blocked by default for security. This repo sets `"markdown.preview.security.level": "allowInsecureContent"` in `.vscode/settings.json` so local `./assets/*.svg` images render. If previews still show broken icons, run **Markdown: Change preview security settings** from the command palette and choose *Allow insecure content*, then reopen the preview.
- For [core-stack.org](https://core-stack.org/) publication, convert markdown to site CMS or paste into a blog post with uploaded SVG/PNG exports.
