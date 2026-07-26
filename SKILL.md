---
disable-model-invocation: true
name: image-edit
description: "image, edit, mosaic, part, blur, sensitive, info"
version: 0.2.0
tools: Bash, Read, Write, sandbox_execute
---

# Image Edit — Programmatic Image Manipulation

Edit images with Python Pillow: mosaic/blur regions, draw annotations, crop, resize, and generate before/after comparison strips for verification.

## Agent Delegation

All image editing processing delegates to the `media` agent (Haiku, maxTurns=10).
Main context handles user interaction and parameter clarification only.

```
Main context (parse request, clarify params)
  └─ Task(subagent_type: media, prompt: "[specific operation]...")
```

For batch operations, spawn parallel media agents (one per file).

## Prerequisites

```bash
~/.local/bin/python3 -c "from PIL import Image" 2>/dev/null || \
  pip3 install Pillow --break-system-packages
```

## Core Operations

> **Sandbox acceleration**: When processing 3+ images in batch, use `sandbox_execute` to run all Pillow operations in a single call and return structured summaries — avoids loading raw image data into main context.

### Mosaic (Pixelation)

The primary privacy protection technique. Pattern: resize down → resize back up with NEAREST.

```python
def apply_mosaic(image, region, block_size=8):
    x1, y1, x2, y2 = region
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(image.width, x2), min(image.height, y2)
    crop = image.crop((x1, y1, x2, y2))
    w, h = crop.size
    if w <= 0 or h <= 0:
        return
    small = crop.resize((max(1, w // block_size), max(1, h // block_size)), Image.NEAREST)
    mosaic = small.resize((w, h), Image.NEAREST)
    image.paste(mosaic, (x1, y1))
```

**block_size guide:**
| block_size | Effect | Use Case |
|-----------|--------|----------|
| 4-6 | Light pixelation | Small text, subtle |
| 8-10 | Standard | Usernames, short text |
| 12-16 | Heavy | Faces, large regions |
| 20+ | Maximum | Complete unreadability |

### Gaussian Blur (Alternative)

```python
from PIL import ImageFilter
region = img.crop(box)
blurred = region.filter(ImageFilter.GaussianBlur(radius=15))
img.paste(blurred, (box[0], box[1]))
```

### Background-sample Redaction (Natural De-identification)

When you want the result to look like a *genuine screenshot of a fake account*
rather than an obviously censored one: sample the local background colour, fill
over the original text, and write a fake replacement in its place. Avatars
become flat monogram circles (default-avatar style). Choose this over mosaic
when the screenshot will be shared publicly (blog, social, docs) and a censored
look is undesirable.

Implemented in **`scripts/redact.py`** (reusable module + CLI). It owns the
fiddly mechanics; *which* regions and *what* replacements remain caller
decisions (OCR auto-locates ASCII emails; name/avatar regions are a judgement
call).

```bash
# CLI — auto path: OCR every email and replace with fake ones
~/.local/bin/python3 scripts/redact.py shot.png --out shot_deid.png
```

```python
# Module — full control (emails auto + manual name/avatar regions)
from redact import RedactCanvas, fake_identities
c = RedactCanvas("shot.png")
ids = fake_identities(6)                       # 小明 小華 小美 ... + matching emails
c.auto_redact_emails()                         # OCR + regex, auto-measured bounds
c.redact_text((222, 1142, 645, 1192), "小華")   # rough box → auto-expands to real glyph span
c.monogram_avatar(148, 1193, 54, "華")          # colour disc + letter
c.save("shot_deid.png")
```

**Why a module, not inline (and not an `image-ops` op):** the value is 80%
orchestration (OCR location, fake-name mapping, font, coordinate decisions),
which doesn't belong in the pure-pixel `image-ops` layer. Keep it here.

**Robustness notes (learned the hard way):**
- `redact_text` **auto-measures the real text extent** (`measure_bounds`) and
  expands the fill box — hand-estimated boxes clip glyph tails (e.g. a trailing
  `！`). Never trust an eyeballed width.
- `sample_bg` takes the median of a box's top/bottom edge strips, so it adapts
  per-container (header sheet vs card vs body) automatically.
- Fonts resolve through a **fallback chain** (STHeiti → Hiragino → PingFang →
  Noto); `PingFang.ttc` is absent on some macOS installs — don't hard-code it.
- Palette matches dark-mode UIs: primary text `(232,234,237)`, secondary/email
  `(154,160,166)`. Adjust for light themes.
- Verify like any redaction: re-run OCR on the output, assert no original PII
  string survives.

### Annotation (Red Boxes, Labels)

For marking regions before applying edits (preview/verification):

```python
from PIL import ImageDraw
draw = ImageDraw.Draw(img)
draw.rectangle([(x1, y1), (x2, y2)], outline='red', width=2)
draw.text((x1, y1 - 14), 'Label', fill='red')
```

### Comparison Strip (Before/After Verification)

Generate side-by-side zoomed crops for verification:

```python
def make_comparison(original, edited, box, scale=3):
    crop_orig = original.crop(box)
    crop_edit = edited.crop(box)
    w, h = crop_orig.size
    orig_big = crop_orig.resize((w * scale, h * scale), Image.NEAREST)
    edit_big = crop_edit.resize((w * scale, h * scale), Image.NEAREST)
    gap = 20
    combined = Image.new('RGBA', (w * scale * 2 + gap, h * scale), (40, 40, 40, 255))
    combined.paste(orig_big, (0, 0))
    combined.paste(edit_big, (w * scale + gap, 0))
    return combined
```

## Workflow: Targeted Mosaic (Complete)

The full workflow combining OCR + Image Edit for privacy protection:

1. **Detect** — Use `/ocr` skill to find target text positions
2. **Preview** — Draw red rectangles on copy, save as `_preview.png`
3. **Apply** — Apply mosaic to each detected region with padding
4. **Verify** — Generate comparison strips for each region group
5. **Final Check** — Re-run OCR on output to confirm text is unreadable
6. **Clean up** — Delete preview and comparison files

### Sub-Region Calculation

When OCR returns a long string containing the target (e.g., `/Users/joneshong/.claude/...`), calculate the sub-region for just the target word:

```python
def sub_region(full_text, keyword, x, y, w, h, pad=6):
    idx = full_text.lower().find(keyword.lower())
    if idx < 0:
        return None
    char_w = w / len(full_text)
    sx = x + int(idx * char_w)
    sw = int(len(keyword) * char_w)
    return (sx - pad, y - pad, sx + sw + pad, y + h + pad)
```

## Color Space Handling

Important: handle RGBA properly to avoid black backgrounds:

```python
# Safe RGBA → RGB conversion (white background)
if img.mode == 'RGBA':
    rgb = Image.new('RGB', img.size, (255, 255, 255))
    rgb.paste(img, mask=img.split()[3])
    img = rgb
```

## Resampling Filter Selection

| Filter | Speed | Quality | When |
|--------|-------|---------|------|
| NEAREST | Fastest | Blocky | Mosaic effect, pixel art |
| BILINEAR | Fast | OK | Quick thumbnails |
| BICUBIC | Medium | Good | General resize |
| LANCZOS | Slow | Best | Final output, photos |

## Parallel Processing with /team-tasks

For editing multiple images or applying many operations:
```
/team-tasks
Mode: DAG
- Agent 1: Detect all target regions (OCR)
- Agent 2: Apply mosaic to regions (depends on Agent 1)
- Agent 3: Generate comparison strips + verify (depends on Agent 2)
```

For batch processing multiple images:
```
/team-tasks
Mode: DAG
- Agent per image: detect + mosaic + verify independently
- Final agent: merge all outputs
```

## Sandbox Optimization

Batch operations benefit from `sandbox_execute`:

- **Batch image processing**: Process multiple images (mosaic, blur, annotate, resize) in one sandbox call, returning structured summaries instead of raw image data
- Saves context tokens when handling 3+ images simultaneously

Principle: **Deterministic batch work → sandbox; reasoning/presentation → LLM.**

## Continuous Improvement

This skill evolves with each use. After every invocation:

1. **Reflect** — Identify what worked, what caused friction, and any unexpected issues
2. **Record** — Append a concise lesson to `lessons.md` in this skill's directory
3. **Refine** — When a pattern recurs (2+ times), update SKILL.md directly

### lessons.md Entry Format

```
### YYYY-MM-DD — Brief title
- **Friction**: What went wrong or was suboptimal
- **Fix**: How it was resolved
- **Rule**: Generalizable takeaway for future invocations
```

Accumulated lessons signal when to run `/skill-optimizer` for a deeper structural review.

## Additional Resources

### Reference Files
- **`references/pillow-guide.md`** — Detailed Pillow operations, format handling, coordinate system
