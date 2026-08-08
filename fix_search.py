import glob, os

svg_search = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16" style="vertical-align: middle;"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>'
magnifying_glass = '\U0001f50d'

for f in glob.glob(r'C:\Users\danat\Desktop\dvachbot\site_tgach\templates\*.jinja2'):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    if magnifying_glass in content:
        content = content.replace(magnifying_glass, svg_search)
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print('Fixed magnifying glass in', os.path.basename(f))
