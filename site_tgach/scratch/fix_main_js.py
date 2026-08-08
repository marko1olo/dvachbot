"""
Apply the same catalog video fix to main.js.
"""
import sys, gzip, os

path = r'C:\Users\danat\Desktop\dvachbot\site_tgach\static\js\main.js'

with open(path, 'rb') as f:
    raw = f.read()

# Find the isVid block
idx = raw.find(b'} else if (isVid) {')
if idx < 0:
    sys.stdout.buffer.write(b'isVid block NOT found in main.js!\n')
    sys.stdout.buffer.flush()
    exit(1)

end_marker = b"                }\r\n            } else {\r\n"
end_idx = raw.find(end_marker, idx)
if end_idx < 0:
    # Try LF variant
    end_marker = b"                }\n            } else {\n"
    end_idx = raw.find(end_marker, idx)

if end_idx < 0:
    sys.stdout.buffer.write(b'End marker NOT found!\n')
    # Show surrounding
    sys.stdout.buffer.write(('isVid found at ' + str(idx) + '\n').encode())
    sys.stdout.buffer.write(('Context: ' + repr(raw[idx:idx+600]) + '\n').encode('utf-8'))
    sys.stdout.buffer.flush()
    exit(1)

block_end = end_idx + len(b"                }")
OLD_BLOCK = raw[idx:block_end]
sys.stdout.buffer.write(f'OLD block: [{idx}, {block_end}), len={len(OLD_BLOCK)}\n'.encode())

# Check if it has the old code
if b'background-color: #000' not in OLD_BLOCK and b'posterUrl' not in OLD_BLOCK:
    sys.stdout.buffer.write(b'[INFO] main.js may already be patched or is different.\n')
    sys.stdout.buffer.write(repr(OLD_BLOCK[:200]).encode('utf-8'))
    sys.stdout.buffer.flush()
    exit(0)

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

# Try with CRLF and LF end_marker
lf_end_marker = b"                }\n            } else {\n"
if end_marker == lf_end_marker:
    # LF file
    NEW_BLOCK = NEW_BLOCK.replace(b'\r\n', b'\n')

new_raw = raw[:idx] + NEW_BLOCK + raw[block_end:]
with open(path, 'wb') as f:
    f.write(new_raw)

sys.stdout.buffer.write(f'[OK] main.js written. Size: {len(new_raw)}\n'.encode())

# Regenerate gzip
gz_path = path + '.gz'
with gzip.open(gz_path, 'wb', compresslevel=9) as gz:
    gz.write(new_raw)
sys.stdout.buffer.write(f'[OK] main.js.gz regenerated. Size: {os.path.getsize(gz_path)}\n'.encode())

# Verify
sys.stdout.buffer.write(f'has_thumbForOverlay: {b"thumbForOverlay" in new_raw}\n'.encode())
has_old_poster = b'posterUrl' in new_raw
sys.stdout.buffer.write(f'has_old_poster: {has_old_poster}\n'.encode())
sys.stdout.buffer.flush()
