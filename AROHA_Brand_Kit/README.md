# AROHA Brand Kit

This package is rebuilt around the supplied construction sheets and master reference artwork.

## Source of truth
- `01_MASTER_LOGOS/SVG/AROHA_Horizontal_Full_Color.svg`
- `02_SYMBOL/SVG/AROHA_Symbol_Full_Color.svg`

Both are genuine SVG path artwork with no embedded raster images. The wordmark and tagline are outlined paths, so no live font dependency is required.

## Construction specifications supplied
### Symbol
- Grid radius: 500 units
- Centre: (500, 500)
- Arms: 41 degrees
- Uniform gap: 68 units
- Apex fillets: 173 units (amber) / 105 units (green), concentric and separated by the gap
- Corner fillet: 30 units
- Sharp apex heights above centre: amber 190; green 100
- Shared fillet centre y: 539

### Wordmark
- A cap height: 455 units
- A apex: 37 units
- A edge slope: 1:2 (26.6 degrees)
- A stroke: 74 units, perpendicular
- R bowl radius: 137 units
- R leg angle: 36.5 degrees from vertical
- O: true circle, diameter 468 units
- H bar: 70 units
- H stem: 74 units
- Letter gaps: 107 / 98 / 140 / 100 units
- Tagline: Montserrat Medium (500), tracking 0.22em, word space +0.24em
- Tagline cap height: 106 units (0.232 × wordmark cap)
- Tagline supplied as outlined paths

## Palette
- Forest green: #073F32
- Solar amber: #E6A43A
- Warm ivory: #F7F5EF
- Charcoal: #111111
- White: #FFFFFF

## Folder guide
- `01_MASTER_LOGOS`: primary horizontal logo
- `02_SYMBOL`: standalone symbol
- `03_LOGO_VARIANTS`: single-colour symbol and horizontal lockups
- `04_APP_ICONS`: square app icon variants
- `05_FAVICONS`: SVG, ICO and PNG sizes
- `06_BRAND_GUIDELINES`: PDF and detailed notes
- `07_PREVIEWS`: review sheet
- `08_SOURCE_FILES`: supplied construction references, master PNGs, draft SVGs and prior kit for traceability

## Usage
Use SVG for websites, print workflows and scaling. Use PNG for applications that require raster assets. For transparent placement, use the PNG exports or SVG masters; app icons intentionally have solid backgrounds.

The original uploaded construction sheets and draft files are retained unchanged in `08_SOURCE_FILES`.
