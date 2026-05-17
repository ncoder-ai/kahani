# Mobile App Assets

Source images used by `@capacitor/assets` to generate iOS app icons and splash screens at all required sizes.

## Files

- `logo.png` — 2048×2048 PNG, **transparent background**, Kahani wordmark centered. Used by the asset generator in Easy Mode to composite onto the brand background color (`#0a0a0f`) for both icons and splash screens.

## Regenerate native assets

On a Mac (after `git pull`):

```bash
cd frontend
npm install --legacy-peer-deps
npm run assets:generate
```

This rewrites `frontend/ios/App/App/Assets.xcassets/AppIcon.appiconset/` and `Splash.imageset/` with all sizes Apple requires (iPhone, iPad, marketing, etc.). Commit the regenerated `ios/App/App/Assets.xcassets/` and rebuild from Xcode.

## Updating the logo

The current `logo.png` is generated from the wide banner at `frontend/public/kahanilogo.png` (1613×451) centered on a 2048×2048 transparent canvas with a small margin. To re-derive:

```python
from PIL import Image
src = Image.open('public/kahanilogo.png').convert('RGBA')
sw, sh = src.size
OUT = 2048
canvas = Image.new('RGBA', (OUT, OUT), (0, 0, 0, 0))
target_w = int(OUT * 0.92)
scale = target_w / sw
target_h = int(sh * scale)
logo = src.resize((target_w, target_h), Image.LANCZOS)
canvas.alpha_composite(logo, ((OUT - target_w) // 2, (OUT - target_h) // 2))
canvas.save('assets/logo.png', 'PNG', optimize=True)
```

For a proper App Store-quality icon, replace `logo.png` with bespoke artwork: a square 1024×1024+ PNG designed to look good as a tiny home-screen icon (the current wide-banner approach makes the icon read poorly at small sizes).

## Brand colors

- Background: `#0a0a0f` (near-black)
- Gradient accents: `#a78bfa` (purple) → `#ec4899` (pink)
