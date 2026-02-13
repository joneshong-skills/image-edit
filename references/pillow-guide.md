# Pillow Guide — Detailed Image Manipulation Reference

Comprehensive guide for advanced Pillow operations in image editing workflows.

## Mosaic/Pixelation Technique

The two-step resize creates the blocky pixelated effect:

```python
# Step 1: Shrink down (destroys detail)
small = crop.resize((w // block_size, h // block_size), Image.NEAREST)

# Step 2: Scale back up (creates blocks)
mosaic = small.resize((w, h), Image.NEAREST)
```

**Why NEAREST filter?** Other filters (BILINEAR, BICUBIC) smooth/interpolate pixels, creating gradients instead of sharp blocks.

**Block size selection:**
- Text height 10-15px → block_size=8
- Text height 16-24px → block_size=10
- Text height 25-40px → block_size=12
- Faces/large regions → block_size=16+

**Edge case handling:**
```python
# Prevent division by zero and negative dimensions
w, h = max(1, crop.width), max(1, crop.height)
small_w = max(1, w // block_size)
small_h = max(1, h // block_size)
```

## Gaussian Blur Parameters

Blur radius determines the effect strength:

| Radius | Effect | Use Case |
|--------|--------|----------|
| 5-8 | Subtle | Light privacy, background elements |
| 10-15 | Standard | General blur, moderate privacy |
| 20-30 | Strong | Heavy blur, maximum privacy |
| 40+ | Extreme | Artistic effects |

**Performance note:** Blur is slower than mosaic. For batch processing, prefer mosaic.

## ImageDraw Complete API

### Rectangles and Boxes

```python
from PIL import ImageDraw
draw = ImageDraw.Draw(img)

# Basic rectangle
draw.rectangle([(x1, y1), (x2, y2)], outline='red', width=2)

# Filled rectangle
draw.rectangle([(x1, y1), (x2, y2)], fill=(255, 0, 0, 128))

# Rounded rectangle (Pillow 8.2+)
draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=10, outline='blue', width=3)
```

### Text Annotation

```python
from PIL import ImageFont

# System font
font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=14)

# Draw text with background
text = "Region 1"
bbox = draw.textbbox((x, y), text, font=font)
draw.rectangle(bbox, fill='white')
draw.text((x, y), text, fill='red', font=font)
```

### Lines and Shapes

```python
# Line
draw.line([(x1, y1), (x2, y2)], fill='green', width=3)

# Polygon
draw.polygon([(x1, y1), (x2, y2), (x3, y3)], outline='blue', fill='yellow')

# Ellipse
draw.ellipse([(x1, y1), (x2, y2)], outline='purple', width=2)
```

## Comparison Strip Pattern

Side-by-side zoomed comparison for verification:

```python
def make_comparison(original, edited, box, scale=3):
    # Extract and zoom both versions
    crop_orig = original.crop(box)
    crop_edit = edited.crop(box)
    w, h = crop_orig.size

    orig_big = crop_orig.resize((w * scale, h * scale), Image.NEAREST)
    edit_big = crop_edit.resize((w * scale, h * scale), Image.NEAREST)

    # Create canvas with gap
    gap = 20
    combined = Image.new('RGBA', (w * scale * 2 + gap, h * scale), (40, 40, 40, 255))

    # Paste side by side
    combined.paste(orig_big, (0, 0))
    combined.paste(edit_big, (w * scale + gap, 0))

    return combined
```

**Scale factor guide:**
- scale=2 → Good for large text (20px+)
- scale=3 → Standard for most text (12-20px)
- scale=4-5 → Small text (<12px)

## Color Space RGBA/RGB Handling

### The Black Background Problem

When saving RGBA images as JPEG or processing with certain libraries:

```python
# BAD: Direct save creates black background
img.save('output.jpg')  # Transparency → black

# GOOD: White background conversion
if img.mode == 'RGBA':
    rgb = Image.new('RGB', img.size, (255, 255, 255))
    rgb.paste(img, mask=img.split()[3])
    img = rgb
img.save('output.jpg')
```

### Color Tuple Formats

```python
# RGB: 3-tuple
color = (255, 0, 0)  # Red

# RGBA: 4-tuple (alpha: 0=transparent, 255=opaque)
color = (255, 0, 0, 128)  # Semi-transparent red

# Named colors (ImageDraw only)
draw.rectangle(box, outline='red')
```

## Batch Region Processing

Efficient pattern for applying operations to multiple regions:

```python
# Collect all regions first
regions = [
    (10, 20, 100, 40),
    (150, 60, 300, 90),
    (50, 150, 200, 180)
]

# Apply mosaic to all
for region in regions:
    apply_mosaic(img, region, block_size=10)

# Generate verification strips
strips = []
for i, region in enumerate(regions):
    strip = make_comparison(original, img, region, scale=3)
    strips.append(strip)
    strip.save(f'verify_{i}.png')
```

## Image Format Considerations

### PNG vs JPEG

| Format | Transparency | Compression | Use Case |
|--------|-------------|-------------|----------|
| PNG | Yes (RGBA) | Lossless | Screenshots, text, transparency |
| JPEG | No | Lossy | Photos, gradients, no transparency |

### Quality Settings

```python
# JPEG quality (1-100, higher = better quality, larger file)
img.save('output.jpg', quality=95)  # High quality
img.save('output.jpg', quality=85)  # Standard
img.save('output.jpg', quality=70)  # Lower quality, smaller

# PNG compression (0-9, higher = smaller file, slower)
img.save('output.png', compress_level=6)  # Default
img.save('output.png', compress_level=9)  # Maximum compression
```

### Metadata Preservation

```python
# Copy EXIF data from original
exif = original.info.get('exif')
if exif:
    img.save('output.jpg', exif=exif)
```

## Coordinate System

Pillow uses standard image coordinates:

```
(0, 0) ────────── (width, 0)
  │                    │
  │    (x, y)         │
  │                    │
(0, height) ── (width, height)
```

**Box format:** `(x1, y1, x2, y2)` where:
- `(x1, y1)` = top-left corner
- `(x2, y2)` = bottom-right corner (exclusive)

**Validation:**
```python
# Ensure box is within image bounds
x1, y1 = max(0, x1), max(0, y1)
x2, y2 = min(img.width, x2), min(img.height, y2)

# Check valid dimensions
if x2 <= x1 or y2 <= y1:
    raise ValueError("Invalid box dimensions")
```

## Resampling Filters Comparison

| Filter | Quality | Speed | Algorithm | Best For |
|--------|---------|-------|-----------|----------|
| NEAREST | Blocky | Fastest | Pick closest pixel | Pixel art, mosaic effect |
| BOX | Low | Fast | Average box of pixels | Quick downscaling |
| BILINEAR | Medium | Fast | Linear interpolation 2x2 | Thumbnails |
| HAMMING | Medium | Medium | Hamming window | General purpose |
| BICUBIC | Good | Medium | Cubic interpolation 4x4 | Photos, general resize |
| LANCZOS | Best | Slow | Lanczos window 6x6 | Final output, high quality |

**Rule of thumb:**
- Upscaling → LANCZOS or BICUBIC
- Downscaling → LANCZOS (best), BICUBIC (good), BOX (fast)
- Pixel-perfect → NEAREST
