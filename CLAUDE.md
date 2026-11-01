# Cog repo rules

This repo holds exactly **one** Red-DiscordBot (3.5.x) cog. Pushes to the default branch are
deployed to the prod bot automatically by the conductor cog, so `main` must always load.

## Layout

```
info.json          repo metadata
README.md          commands, events emitted, public methods (keep it current)
<name>/__init__.py async def setup(bot): await bot.add_cog(...)
<name>/<name>.py   the Cog class
<name>/info.json   name, short, description, requirements (pip), end_user_data_statement
```

Repo name is `cog-<name>`, the package folder and cog name are `<name>`.

## Rules

- **Commands** are prefixed with the cog name: `<name>`, `<name> stats`, ... (use a
  `commands.group`). Prefix commands only, no slash commands for now.
- **State**: Red `Config` only (`Config.get_conf(self, identifier=<unique int>)`).
  No files on disk, no module-level mutable globals.
- **Secrets**: `await self.bot.get_shared_api_tokens("<service>")`. The owner sets them once
  with `[p]set api <service> key,<value>`. Never commit secrets.
- **Background loops**: start them in `__init__` / `cog_load`, and **cancel them in
  `cog_unload`**. The conductor reloads cogs often; leaked tasks run twice.
- **No blocking calls** in the event loop (`requests`, `time.sleep`, heavy CPU). Use
  `aiohttp`, `asyncio.sleep`, or `asyncio.to_thread`.
- **Pip dependencies** go in `<name>/info.json` → `requirements`.
- **Other cogs**:
  - Events (default): `self.bot.dispatch("<name>_<event>", ...)`; listen with
    `@commands.Cog.listener() async def on_<other>_<event>(...)`.
  - Queries: `self.bot.get_cog("Name")` at call time; handle `None`; never store it.
  - Shared code: a separate pip-installable repo pinned by tag in `requirements`.
  - Never read another cog's `Config`, never import another cog's module, never depend on
    load order.
- Keep `README.md` in sync: commands, events emitted, public methods.

## Testing

Test on the dev bot first: the cog folder lives in `~/Projects/cogged-up/my-cogs/` and the dev
conductor reloads it within ~2 s of saving. Syntax/load errors are DMed to the owner and the
old version keeps running. Then `git push`.

## Rollback

`POST /cogs/<name>/rollback {"commit": "<sha>"}` on the conductor API, or
`[p]conductor rollback <name> <sha>` in Discord. `.../unpin` resumes auto-updates.
