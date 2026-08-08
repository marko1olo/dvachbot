import sys
path = r'C:\Users\danat\Desktop\dvachbot\site_tgach\static\js\main.src.js'
with open(path, 'rb') as f:
    raw = f.read()

has_old = b'preload="metadata" muted playsinline loop data-src="${vidUrl}" ${posterUrl' in raw
has_new = b'thumbForOverlay' in raw
has_overlay = b'overlayHtml' in raw
has_typeBadges = b"if (tt === 'image') typeBadges" in raw
has_black_bg = b'background-color: #000;' in raw

print('has_old_catalog_poster:', has_old)
print('has_new_thumbForOverlay:', has_new)
print('has_overlayHtml:', has_overlay)
print('has_typeBadges:', has_typeBadges)
print('has_black_bg_in_catalog:', has_black_bg)
print('File size:', len(raw))
