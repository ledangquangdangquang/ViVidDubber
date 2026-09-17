# CLAUDE.md

See `AGENTS.md` for the full project guide (pipeline, job queue, providers, editing conventions,
communication mode). That file is the source of truth — keep this one short and don't duplicate it.

## UI work

Any UI change to `web.html` goes through the `hallmark` skill (`.claude/skills/hallmark`), see
AGENTS.md § "UI changes: use the Hallmark skill". Load it before touching CSS/markup, even for a
small fix — the page already has a locked Catppuccin Mocha design system (`tokens.css` + the stamp
comment at the top of `web.html`'s `<style>` block); don't invent new colors, fonts, or inline
styles outside it.
