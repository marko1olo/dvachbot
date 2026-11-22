import pytest
import os
import time

def test_mobile_show_floating_change():
    main_js_path = r'c:\dev\dvachbot\site_tgach\static\js\main.js'
    with open(main_js_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check that the change was applied
    assert 'if (this.floatingBox) {' in content
    assert 'if (this.floatingBox && window.innerWidth > 768) {' not in content

def test_minified_files_updated():
    js_dir = r'c:\dev\dvachbot\site_tgach\static\js'
    main_js = os.path.join(js_dir, 'main.js')
    main_min_js = os.path.join(js_dir, 'main.min.js')
    
    # Allow small difference due to filesystem time resolution
    assert os.path.getmtime(main_min_js) >= os.path.getmtime(main_js) - 1
