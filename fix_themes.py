import os

hotfixes = '''
/* =========================
   HOTFIXES FOR THEMES (UI REMEDIATION)
   ========================= */

/* 1. Sakura & Ocean: контрастность текста плейсхолдеров */
html.theme-sakura ::placeholder { color: rgba(160,80,112,0.85) !important; }
html.theme-ocean ::placeholder { color: rgba(137,180,250,0.8) !important; }

/* 2. Sakura & Ocean: отбалансировать паддинги боковых блоков */
html.theme-sakura .panel, html.theme-ocean .panel,
html.theme-sakura .sidebar, html.theme-ocean .sidebar {
    padding: 15px !important;
}

/* 3. Sakura: убрать dashed рамку с картинок */
html.theme-sakura .post-image, html.theme-sakura .file-thumb img {
    border-style: solid !important;
}

/* 4. Lain & Gruvbox: исправить контраст ссылок, окантовки блоков и тегов <Protocol> */
html.theme-lain a, html.theme-gruvbox a {
    color: var(--accent-link) !important;
}
html.theme-lain .protocol-tag { color: #ff3333 !important; }
html.theme-gruvbox .protocol-tag { color: #fb4934 !important; }
html.theme-lain .post, html.theme-gruvbox .post {
    border-color: var(--border-primary) !important;
}

/* 5. Win95: отбалансировать [+], паддинги шапок постов, выпадающие списки */
html.theme-win95 .thread-toggle {
    display: inline-flex; align-items: center; justify-content: center;
    width: 20px; height: 20px; vertical-align: middle;
}
html.theme-win95 .post-header {
    padding: 4px 8px !important;
}
html.theme-win95 select {
    padding: 2px 4px !important;
    appearance: menulist !important;
}

/* 6. Noir: убрать принудительный CAPS у кнопок, восстановить маскота */
html.theme-noir button, html.theme-noir .btn {
    text-transform: none !important;
}
html.theme-noir .mascot-container { display: block !important; }

/* 7. Terminal & Cyberpunk: читаемость ссылок [на главную] (top-nav links) */
html.theme-terminal .top-nav a, html.theme-cyberpunk .top-nav a,
html.theme-terminal .header-group a, html.theme-cyberpunk .header-group a {
    color: var(--accent-primary) !important;
    text-shadow: 1px 1px 0px #000;
}
'''

files = [
    r'C:\Users\danat\Desktop\dvachbot\site_tgach\static\css\style.src.css',
    r'C:\Users\danat\Desktop\dvachbot\site_tgach\static\css\style.css',
    r'C:\Users\danat\Desktop\dvachbot\site_tgach\static\css\style.min.css'
]

for path in files:
    with open(path, 'a', encoding='utf-8') as file:
        file.write('\n' + hotfixes)
    print(f'Appended hotfixes to {os.path.basename(path)}')
