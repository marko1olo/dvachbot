import os

js_code = """
document.addEventListener("DOMContentLoaded", function() {
    if (localStorage.getItem('ru_vpn_alert_shown')) {
        return; // Already shown or checked
    }
    fetch('/api/is-ru')
        .then(res => res.json())
        .then(data => {
            if (data.is_ru) {
                const alertDiv = document.createElement('div');
                alertDiv.innerHTML = "путин хуйло, включи ВПН, иначе не загрузятся картинки! кек";
                alertDiv.style.position = "fixed";
                alertDiv.style.top = "10px";
                alertDiv.style.left = "10px";
                alertDiv.style.backgroundColor = "rgba(255, 0, 0, 0.9)";
                alertDiv.style.color = "white";
                alertDiv.style.padding = "10px 15px";
                alertDiv.style.borderRadius = "5px";
                alertDiv.style.zIndex = "999999";
                alertDiv.style.fontWeight = "bold";
                alertDiv.style.boxShadow = "0 4px 6px rgba(0,0,0,0.3)";
                alertDiv.style.transition = "opacity 0.5s";
                document.body.appendChild(alertDiv);
                
                setTimeout(() => {
                    alertDiv.style.opacity = "0";
                    setTimeout(() => alertDiv.remove(), 500);
                }, 6000);
            }
            // Optionally set flag to not show again this session:
            // sessionStorage.setItem('ru_vpn_alert_shown', '1');
        })
        .catch(err => console.error("Error checking ru status:", err));
});
"""

for js_file in ['site_tgach/static/js/main.js', 'Dubsite_tgach/static/js/main.js']:
    if os.path.exists(js_file):
        with open(js_file, 'a', encoding='utf-8') as f:
            f.write(js_code)
        print(f"Appended to {js_file}")
    else:
        print(f"File not found: {js_file}")
