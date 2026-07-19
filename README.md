# Image Edit

Programmatic image manipulation using Python Pillow: mosaic/blur regions, draw annotations, crop, resize, and generate before/after comparison strips for verification.

## Quick Start

```bash
# Check dependencies
~/.local/bin/python3 -c "from PIL import Image" 2>/dev/null || \
  pip3 install Pillow --break-system-packages
```

## Core Operations

### Mosaic (Pixelation)
Primary privacy protection technique using block-based pixelation:
- Resize region down → resize back up with NEAREST filter
- Adjustable block sizes: 4-6 (subtle), 8-10 (standard), 12-16 (heavy), 20+ (maximum)

### Gaussian Blur
Alternative privacy technique using PIL's `ImageFilter.GaussianBlur`:
- Configurable blur radius for smooth anonymization

### Annotation
Mark regions before applying edits:
- Red boxes for highlighting
- Text labels for identification
- Used for preview/verification

### Comparison Strip
Side-by-side zoomed crops for verification:
- Before/after visual comparison
- Scaled for easy inspection
- Confirms privacy protection effectiveness

## Workflow: Targeted Mosaic

1. **Detect** — Use `/ocr` skill to find target text positions
2. **Preview** — Draw red rectangles on copy, save as `_preview.png`
3. **Apply** — Apply mosaic to each detected region with padding
4. **Verify** — Generate comparison strips for each region group
5. **Final Check** — Re-run OCR on output to confirm text is unreadable

## Key Features

- **Flexible Filters**: NEAREST (mosaic), BILINEAR, BICUBIC, LANCZOS (quality resize)
- **RGBA Support**: Proper color space handling to avoid black backgrounds
- **Batch Processing**: Parallel processing via `/team-tasks` for multiple images
- **Verification**: Re-run OCR to confirm privacy protection success

## Use Cases

- Mosaic sensitive information in screenshots
- Blur PII before sharing documentation
- Annotate and redact images
- Create comparison strips for before/after verification
- Batch process multiple images in parallel

## Integration

- Works with **ocr** skill for text detection and positioning
- Pairs with **team-tasks** for parallel batch processing
- Use with **image-gen** for follow-up visual generation

## License

Included in Claude Code as part of the Skills Collection.
