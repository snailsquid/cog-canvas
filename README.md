# mycog

Example cog created from `cog-template`. Replace this README when you build the real cog.

## Commands

| Command | Who | What |
|---|---|---|
| `[p]mycog` | anyone | Says hello and increments a counter. |
| `[p]mycog reset` | owner | Resets the counter. |

## Events emitted

| Event | Listener signature | When |
|---|---|---|
| `mycog_hello` | `on_mycog_hello(self, user: discord.abc.User, count: int)` | After `[p]mycog` runs. |

## Public methods

None.

## Secrets

None. (If needed: `[p]set api <service> key,<value>`, read with `bot.get_shared_api_tokens("<service>")`.)
