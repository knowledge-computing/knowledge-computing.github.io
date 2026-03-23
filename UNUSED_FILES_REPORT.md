# Unused Files Report

This report identifies files that appear to be unused in the repository.

## Definitely Unused Files (Safe to Delete)

### Documentation/Utility Files
1. **`compression.ipynb`** - Jupyter notebook for one-time image compression task
2. **`features.txt`** - Theme documentation/notes, not used by the site
3. **`readme`** - Theme documentation, not used by the site
4. **`scripts/render_module.rb`** - Ruby utility script not referenced anywhere

### Unused Image Files
5. **`images/background/shutterstock_1728128539.eps`** - EPS format file, not referenced (only JPEG/PNG used)
6. **`images/research/dummy_pic_ps.psd`** - PSD source file, not referenced
7. **`images/sponsors/cls.png`** - Unused (sponsors.yml uses `risksolutions.jpg` instead for CLS)

### People Images
All people images are being kept as requested, even if not currently referenced in `people.yml`. They may be used elsewhere (e.g., `projects/streetlens.html`) or needed for future updates.

Note: `yaoyichiang.jpg` is referenced in `projects/streetlens.html` but the actual file in people.yml is `yao-yi_chiang.jpg` - there may be a filename mismatch.

### Potentially Unused Background Images
- `images/background/slider_air_quality.png` - Not referenced
- `images/background/slider_geobert.png` - Not referenced
- `images/background/shutterstock_1056001967.jpg` - Not referenced
- `images/background/shutterstock_1677933550.jpg` - Not referenced
- `images/background/shutterstock_709991278.jpg` - Not referenced
- `images/background/shutterstock_785666224.jpg` - Not referenced
- `images/background/people.png` - Not referenced (people.html uses GIF instead)

### Potentially Unused Research Images
These exist but may not be in research.yml:
- `images/research/adms.jpg` - Check if used (research.yml has adms.jpg)
- `images/research/adms.png` - Duplicate/alternative format
- `images/research/cedar2.png` - Duplicate/alternative format
- `images/research/complete_ongoing.jpg` - Not referenced
- `images/research/complete_ongoing.png` - Not referenced
- `images/research/detect.jpg` - Check if used (research.yml has detect.jpg)
- `images/research/detect.png` - Duplicate/alternative format
- `images/research/earthscan.png` - Check if used (research.yml has earthscan.png)
- `images/research/geobert.jpg` - Check if used (research.yml has geobert.jpg)
- `images/research/geobert.png` - Duplicate/alternative format
- `images/research/lasi.png` - Check if used (research.yml has lasi.png)
- `images/research/linked_maps.png` - Check if used (research.yml has linked_maps.png)
- `images/research/mint.png` - Check if used (research.yml has mint.png)
- `images/research/mrm.jpeg` - Check if used (research.yml has mrm.jpeg)
- `images/research/ntt.png` - Check if used (research.yml has ntt.png)
- `images/research/physics_ml.gif` - Check if used (research.yml has physics_ml.png)
- `images/research/strabo.jpg` - Check if used (research.yml has strabo.jpg)

## Files That ARE Used (Keep These)

- `publications.bib` - Used by publications.html via bibbase.org
- All CSS files in `css/` directory
- All JavaScript files in `javascripts/` directory
- All YAML data files in `_data/` directory
- `images/knowledge_computing_sticker.jpg` - Used in header
- `images/spatial_computing_sticker.jpg` - Referenced in footer (commented but still present)
- `images/kc-lab-logo_icon.png` - Used as favicon

## Files Deleted

The following files have been deleted:
1. ✅ `compression.ipynb`
2. ✅ `features.txt`
3. ✅ `readme`
4. ✅ `scripts/render_module.rb` (and empty scripts directory)
5. ✅ `images/background/shutterstock_1728128539.eps`
6. ✅ `images/research/dummy_pic_ps.psd`
7. ✅ `images/sponsors/cls.png`
8. ✅ `images/background/slider_air_quality.png`
9. ✅ `images/background/slider_geobert.png`
10. ✅ `images/background/shutterstock_1056001967.jpg`
11. ✅ `images/background/shutterstock_1677933550.jpg`
12. ✅ `images/background/shutterstock_709991278.jpg`
13. ✅ `images/background/shutterstock_785666224.jpg`
14. ✅ `images/background/people.png`
15. ✅ `images/research/adms.png` (duplicate - adms.jpg is used)
16. ✅ `images/research/cedar2.png` (duplicate - cedar.png is used)
17. ✅ `images/research/complete_ongoing.jpg`
18. ✅ `images/research/complete_ongoing.png`
19. ✅ `images/research/detect.png` (duplicate - detect.jpg is used)
20. ✅ `images/research/geobert.png` (duplicate - geobert.jpg is used)
21. ✅ `images/research/physics_ml.gif` (duplicate - physics_ml.png is used)

## Remaining Recommendations

1. **People images**: All people images are being kept as requested, even if not currently referenced in `people.yml`. They may be used elsewhere or needed for future updates.

2. **Check filename mismatches**: `yaoyichiang.jpg` is referenced in `projects/streetlens.html` but the actual file in people.yml is `yao-yi_chiang.jpg` - there may be a filename mismatch that needs to be fixed.

