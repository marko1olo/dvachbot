import os

css_addition = '''
/* CSS Variable Colorization for Logo-Wave */
.header-logo img {
    background-color: var(--accent-primary);
    -webkit-mask: url(/static/logo.png) no-repeat center;
    mask: url(/static/logo.png) no-repeat center;
    -webkit-mask-size: contain;
    mask-size: contain;
    content: url('data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=');
}
'''

for f in ['style.css', 'style.min.css', 'style.src.css']:
    path = os.path.join(r'C:\Users\danat\Desktop\dvachbot\site_tgach\static\css', f)
    with open(path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Fix dock-wave-bg hardcoded color
    content = content.replace('rgba(0,0,0,0.05)', 'var(--border-input)')
    
    # Add logo mask if not already present
    if '.header-logo img {' not in content:
        content += css_addition
        
    with open(path, 'w', encoding='utf-8') as file:
        file.write(content)
print('Fixed logo-wave and dock wave CSS')
