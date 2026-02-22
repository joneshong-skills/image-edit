---
name: image-edit
description: >-
  This skill should be used when the user asks to "mosaic part of an image",
  "blur sensitive info", "pixelate a region", "annotate screenshot",
  "add red boxes to image", "crop and resize image", "combine images",
  "馬賽克", "模糊處理", "圖片標註", "裁切圖片", "圖片編輯",
  "遮蔽敏感資訊", mentions image editing or manipulation,
  or discusses applying visual effects to specific regions of an image.
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
python3 -c "from PIL import Image" 2>/dev/null || \
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
