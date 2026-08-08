path = r'C:\Users\danat\Desktop\dvachbot\site_tgach\static\css\style.css'
with open(path, 'rb') as f:
    content = f.read()
    
# Check CSS rules for loaded video
idx1 = content.find(b'catalog-thumb video.loaded')
if idx1 >= 0:
    print('catalog-thumb video.loaded:', content[idx1:idx1+200].decode('utf-8', errors='replace'))
    
# Also check lazy-load initial opacity
idx2 = content.find(b'.lazy-load')
if idx2 >= 0:
    print('lazy-load rule:', content[idx2:idx2+150].decode('utf-8', errors='replace'))
