import os
import re
import gzip
import sys

def reconfigure_utf8():
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')

def minify_css(css_text):
    # Remove comments
    css_text = re.sub(r'/\*.*?\*/', '', css_text, flags=re.DOTALL)
    # Remove whitespace around delimiters
    css_text = re.sub(r'\s*([\{\}:;])\s*', r'\1', css_text)
    # Replace multiple spaces with single space
    css_text = re.sub(r'\s+', ' ', css_text)
    return css_text.strip()

def main():
    reconfigure_utf8()
    print("🚀 Starting compilation and minification of static assets...")
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(base_dir, "site_tgach", "static")
    css_src = os.path.join(static_dir, "css", "style.src.css")
    css_dest = os.path.join(static_dir, "css", "style.css")
    js_src = os.path.join(static_dir, "js", "main.src.js")
    js_dest = os.path.join(static_dir, "js", "main.js")
    
    # 1. Compile CSS
    if os.path.exists(css_src):
        print(f"Reading CSS source: {css_src}")
        with open(css_src, "r", encoding="utf-8") as f:
            css_content = f.read()
        
        minified_css = minify_css(css_content)
        with open(css_dest, "w", encoding="utf-8") as f:
            f.write(minified_css)
        print(f"✅ Minified CSS written to: {css_dest} ({len(minified_css)} bytes)")
        
        # Gzip CSS
        css_gz = css_dest + ".gz"
        with gzip.open(css_gz, "wb") as f_out:
            f_out.write(minified_css.encode("utf-8"))
        print(f"✅ Gzipped CSS written to: {css_gz}")
    else:
        print(f"⚠️ CSS source not found: {css_src}")
        
    # 2. Compile JS
    if os.path.exists(js_src):
        print(f"Reading JS source: {js_src}")
        with open(js_src, "r", encoding="utf-8") as f:
            js_content = f.read()
            
        with open(js_dest, "w", encoding="utf-8") as f:
            f.write(js_content)
        print(f"✅ JS written to: {js_dest} ({len(js_content)} bytes)")
        
        # Gzip JS
        js_gz = js_dest + ".gz"
        with gzip.open(js_gz, "wb") as f_out:
            f_out.write(js_content.encode("utf-8"))
        print(f"✅ Gzipped JS written to: {js_gz}")
    else:
        print(f"⚠️ JS source not found: {js_src}")

if __name__ == "__main__":
    main()
