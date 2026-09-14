-- UP
-- The Market Canvas tool rail: rays, extended lines, horizontal rays, vertical
-- lines, rectangles, fib retracements, pencil strokes and text join the
-- original horizontal, trendline, range and note. Point counts belong to the
-- validator in tradesync_core.canvas_drawings; this check only keeps a kind the
-- canvas cannot draw out of storage.
--
-- Each version also records how the operator drew it: colour (#rrggbb), width
-- (1-4) and dashed. Null means the version predates styles, and the canvas
-- draws it the way it always has. A drawing is still annotation only.

alter table canvas_drawings drop constraint if exists canvas_drawings_kind_check;
alter table canvas_drawings add constraint canvas_drawings_kind_check
  check (kind in ('horizontal', 'trendline', 'range', 'note', 'ray', 'extended_line',
                  'horizontal_ray', 'vertical', 'rectangle', 'fib_retracement', 'pencil', 'text'));

alter table canvas_drawings add column if not exists style jsonb;
alter table canvas_drawings drop constraint if exists canvas_drawings_style_check;
alter table canvas_drawings add constraint canvas_drawings_style_check
  check (style is null or jsonb_typeof(style) = 'object');

-- DOWN
-- Versions of the newer kinds are history and are not deleted: NOT VALID puts
-- the narrower check back for new rows without rewriting what was recorded.
alter table canvas_drawings drop constraint if exists canvas_drawings_style_check;
alter table canvas_drawings drop column if exists style;
alter table canvas_drawings drop constraint if exists canvas_drawings_kind_check;
alter table canvas_drawings add constraint canvas_drawings_kind_check
  check (kind in ('horizontal', 'trendline', 'range', 'note')) not valid;
