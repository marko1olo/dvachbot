"""
Byte-offset-based replacement - write FIRST, then print.
"""
import sys
path = r'C:\Users\danat\Desktop\dvachbot\site_tgach\static\js\main.src.js'

with open(path, 'rb') as f:
    raw = f.read()

idx = raw.find(b'} else if (isVid) {')
end_marker = b"                }\r\n            } else {\r\n"
end_idx = raw.find(end_marker, idx)
block_end = end_idx + len(b"                }")

OLD_BLOCK = raw[idx:block_end]

NEW_BLOCK = (
    '} else if (isVid) {\r\n'
    '                const vidUrl = mediaUrl;\r\n'
    '                // Use overlay img (NOT poster=) to avoid browser black rect on 404\r\n'
    "                const thumbForOverlay = f.thumbnail_file_id ? `/files/${f.thumbnail_file_id}` : (f.thumbnail_url || '');\r\n"
    '                if (vidUrl) {\r\n'
    '                    const hue = (parseInt(String(threadId).slice(-4), 10) * 137) % 360;\r\n'
    '                    const vidBg = `hsl(${hue},55%,35%)`;\r\n'
    '                    const overlayHtml = thumbForOverlay\r\n'
    "                        ? `<img src=\"${thumbForOverlay}\" style=\"position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;z-index:1;\" loading=\"lazy\" referrerpolicy=\"no-referrer\" onerror=\"this.style.display='none'\">`\r\n"
    '                        : `<div style="position:absolute;top:0;left:0;width:100%;height:100%;z-index:1;display:flex;align-items:center;justify-content:center;"><span style="font-size:2em;">\U0001f3ac</span></div>`;\r\n'
    '                    thumbHtml = `\r\n'
    "                        <div class=\"catalog-thumb lazy-media-wrapper\" data-src=\"${vidUrl}\" data-file-id=\"${f.original_file_id || ''}\" data-type=\"video\" style=\"background-color:${vidBg};\">\r\n"
    '                            ${overlayHtml}\r\n'
    '                            <video class="lazy-load${blurClass}" preload="none" muted playsinline loop data-src="${vidUrl}" style="width:100%;height:100%;object-fit:cover;position:absolute;top:0;left:0;z-index:2;opacity:0;transition:opacity 0.3s;"></video>\r\n'
    '                            <span class="lazy-badge" style="position:absolute;bottom:5px;right:5px;background:rgba(0,0,0,0.6);color:white;padding:2px 4px;font-size:10px;border-radius:3px;z-index:3;">VIDEO</span>\r\n'
    '                        </div>`;\r\n'
    '                } else {\r\n'
    '                     thumbHtml = `<div class="catalog-thumb" style="background-color: ${bgColor}; display:flex; align-items:center; justify-content:center;"><span style="font-size:2em;">\u23f3</span></div>`;\r\n'
    '                }'
).encode('utf-8')

new_raw = raw[:idx] + NEW_BLOCK + raw[block_end:]

# WRITE FIRST
with open(path, 'wb') as f:
    f.write(new_raw)

# Then verify
with open(path, 'rb') as f:
    verify = f.read()
    
has_new = b'thumbForOverlay' in verify
has_old_poster = b'preload="metadata" muted playsinline loop data-src="${vidUrl}" ${posterUrl' in verify
has_black_bg = b'background-color: #000;' in verify

sys.stdout.buffer.write(f'[OK] Written. Size: {len(verify)}\n'.encode('utf-8'))
sys.stdout.buffer.write(f'has_thumbForOverlay: {has_new}\n'.encode('utf-8'))
sys.stdout.buffer.write(f'has_old_poster: {has_old_poster}\n'.encode('utf-8'))
sys.stdout.buffer.write(f'has_black_bg: {has_black_bg}\n'.encode('utf-8'))
sys.stdout.buffer.flush()
