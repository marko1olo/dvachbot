path = r'C:\Users\danat\Desktop\dvachbot\site_tgach\static\js\main.src.js'
with open(path, 'rb') as f:
    raw = f.read()

# Detect line ending
crlf_count = raw.count(b'\r\n')
lf_count = raw.count(b'\n') - crlf_count
print(f'CRLF: {crlf_count}, LF-only: {lf_count}')

content = raw.decode('utf-8')

# Find the isVid block and print exact bytes around it
idx = content.find('} else if (isVid)')
if idx < 0:
    print('isVid NOT found')
else:
    chunk = content[idx:idx+50]
    print(f'Found at {idx}:')
    print(repr(chunk))
    
    # Now try exact match using what we see
    # The file uses LF internally (written by tool that normalizes)
    OLD = "} else if (isVid) {\n                const vidUrl = mediaUrl;\n                const posterUrl = thumbUrl || mediaUrl;\n                if (vidUrl) {\n                    thumbHtml = `\n                        <div class=\"catalog-thumb lazy-media-wrapper\" data-src=\"${vidUrl}\" data-file-id=\"${f.original_file_id || ''}\" data-type=\"video\" style=\"background-color: #000;\">\n                            <video class=\"lazy-load${blurClass}\" preload=\"metadata\" muted playsinline loop data-src=\"${vidUrl}\" ${posterUrl ? `poster=\"${posterUrl}\"` : ''} style=\"width: 100%; height: 100%; object-fit: cover;\"></video>\n                            <span class=\"lazy-badge\" style=\"position:absolute; bottom:5px; right:5px; background:rgba(0,0,0,0.6); color:white; padding:2px 4px; font-size:10px; border-radius:3px;\">VIDEO</span>\n                        </div>`;\n                } else {\n                     thumbHtml = `<div class=\"catalog-thumb\" style=\"background-color: ${bgColor}; display:flex; align-items:center; justify-content:center;\"><span style=\"font-size:2em;\">⏳</span></div>`;\n                }"
    
    if OLD in content:
        print('LF pattern found!')
    else:
        # Print the exact chars in range to compare
        print('LF pattern NOT found. Actual block:')
        print(repr(content[idx:idx+600]))
