# canvas

Renders JSON layout trees (rows, columns, boxes, text, progress bars, grids) to PNG with Pillow.
It is a rendering service: other cogs build a spec and call `render`.

## Commands

| Command | Who | What |
|---|---|---|
| `[p]canvas` | anyone | Usage. |
| `[p]canvas demo` | anyone | Renders a sample showing every node type. |
| `[p]canvas render <json>` | owner | Renders a spec given inline, in a code block, or as a `.json` attachment. |

## Events emitted

None.

## Public methods

```python
canvas = self.bot.get_cog("Canvas")
if canvas is not None:
    png: bytes = await canvas.render(spec)             # raises ValueError on a bad spec
    file: discord.File = await canvas.render_file(spec, "card.png")
```

Rendering runs in a worker thread. The spec is plain dicts/lists, so callers import nothing.

## Spec

```json
{"width": 800, "scale": 2, "background": "#1e1f22", "color": "#ffffff", "root": { ... }}
```

| Key | Default | |
|---|---|---|
| `width` | 800 | in spec units |
| `height` | measured | fixed height; otherwise the root's measured height |
| `scale` | 1 | pixel multiplier (max 4); output is at most 4096 px per side |
| `background` | transparent | |
| `color` | `#ffffff` | default text colour |

Colours are anything Pillow understands: `#rgb`, `#rrggbb`, `#rrggbbaa`, CSS names. Translucent
fills and borders (`#rrggbbaa`) blend with what is underneath.

### Every node

| Key | |
|---|---|
| `type` | `column`, `row`, `box`, `text`, `progress`, `grid`, `spacer` |
| `width`, `height` | fixed size. Without them, columns stretch children to full width, rows to full height, and heights are measured from content. |
| `flex` | share of leftover space: widths in a row (default 1), heights in a column (default 0; spacers 1) |
| `padding` | number, `[vertical, horizontal]` or `[top, right, bottom, left]` |
| `fill`, `border`, `border_width` (2), `radius` | background and outline |

### Node types

| Type | Keys |
|---|---|
| `column` | `children`, `gap`, `align` (`start`/`center`/`end`: placement of children with a fixed `width`) |
| `row` | `children`, `gap`, `align` (placement of children with a fixed `height`) |
| `box` | `child` (one node) |
| `text` | `text` (wraps; `\n` breaks), `size` (16), `weight` (`regular`/`medium`/`bold`), `color`, `align` (`left`/`center`/`right`), `valign` (`top`/`middle`/`bottom`), `line_height` (1.25) |
| `progress` | `value` (0–1), `color`, `track`, `label`, `label_color`, plus the text keys for the label. Default height 32. |
| `grid` | `cells`: list of colour, `null` (empty) or `{"fill", "border"}`. `rows` fills column by column (GitHub style), `cols` fills row by row. `cell` (12), `gap` (3), `cell_radius` (2), `empty` (colour for `null` cells), `align` (center) |
| `spacer` | nothing; takes leftover space |

Fonts: Noto Sans (SIL OFL 1.1, `canvas/data/fonts/OFL.txt`).

## Secrets

None.
