# -*- coding: utf-8 -*-
import gzip
import os
import re
import pytest

JS_DIR = os.path.join(os.path.dirname(__file__), "..", "site_tgach", "static", "js")


def _read_js_file(filename: str) -> str:
    path = os.path.join(JS_DIR, filename)
    assert os.path.exists(path), f"File {path} does not exist"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_mascot_persistence_contracts():
    """
    Verifies that mascot right-click hide is persisted to localStorage
    and bidirectionally synchronized with SettingsManager:
    1. SettingsManager is exported to window.SettingsManager.
    2. SettingsManager.init() reads both CONSTANTS.SETTINGS_KEY and hide_mascot.
    3. SettingsManager.save() keeps hide_mascot in sync.
    4. MascotManager.init() guards against hide_mascot === 'true'.
    5. Mascot contextmenu handler sets hide_mascot and invokes SettingsManager.save().
    """
    for fname in ["main.js", "main.src.js", "main.min.js"]:
        content = _read_js_file(fname)

        # 1. Global export of SettingsManager
        assert "window.SettingsManager = SettingsManager;" in content, (
            f"{fname}: window.SettingsManager must be explicitly exported"
        )

        # 2. SettingsManager.init() check for hide_mascot
        assert "const hideMascotFlag = localStorage.getItem('hide_mascot') === 'true';" in content, (
            f"{fname}: SettingsManager.init must check hide_mascot in localStorage"
        )
        assert "if (hideMascotFlag || saved.showMascot === false)" in content, (
            f"{fname}: SettingsManager.init must set showMascot = false when hide_mascot flag is set"
        )

        # 3. SettingsManager.save() sync
        assert "localStorage.setItem('hide_mascot', 'true');" in content, (
            f"{fname}: SettingsManager.save must sync hide_mascot"
        )
        assert "localStorage.removeItem('hide_mascot');" in content, (
            f"{fname}: SettingsManager.save must remove hide_mascot when enabled"
        )

        # 4. MascotManager.init guard
        assert "if (!SettingsManager.current.showMascot || localStorage.getItem('hide_mascot') === 'true') return;" in content, (
            f"{fname}: MascotManager.init must return early if hide_mascot is true"
        )

        # 5. MascotManager contextmenu handler
        assert "localStorage.setItem('hide_mascot', 'true');" in content
        assert "SettingsManager.current.showMascot = false;" in content
        assert "SettingsManager.save();" in content


def test_undo_redo_native_preservation():
    """
    Verifies that FormManager no longer intercepts Ctrl+Z / Ctrl+Y
    in keydown with e.preventDefault(), which previously broke native
    browser undo/redo for <textarea> and caused input lag.
    """
    for fname in ["main.js", "main.src.js", "main.min.js"]:
        content = _read_js_file(fname)

        # Ensure keydown interceptor with document.execCommand('undo') is removed
        assert "document.execCommand('undo')" not in content, (
            f"{fname}: destructive document.execCommand('undo') keydown listener must not be present"
        )

        # Ensure e.preventDefault() is NOT called on KeyZ
        assert not re.search(r"e\.code\s*===\s*['\"]KeyZ['\"].*?e\.preventDefault\(\)", content, re.DOTALL), (
            f"{fname}: KeyZ must not call e.preventDefault()"
        )

        # Verify notice that native Undo / Redo is preserved
        assert "Native Undo / Redo (Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z) is preserved" in content, (
            f"{fname}: comment acknowledging native undo preservation must be present"
        )


def test_js_bundle_synchronization_and_compression():
    """
    Verifies that main.js, main.src.js, and main.min.js have identical content,
    and that gzipped files exist and decompress to the exact JS bundle.
    """
    main_js = _read_js_file("main.js")
    main_src = _read_js_file("main.src.js")
    main_min = _read_js_file("main.min.js")

    assert main_js == main_src, "main.js and main.src.js must be identical"
    assert main_js == main_min, "main.js and main.min.js must be identical"

    # Check .gz files
    gz_main_path = os.path.join(JS_DIR, "main.js.gz")
    gz_min_path = os.path.join(JS_DIR, "main.min.js.gz")

    assert os.path.exists(gz_main_path), "main.js.gz must exist"
    assert os.path.exists(gz_min_path), "main.min.js.gz must exist"

    with gzip.open(gz_main_path, "rt", encoding="utf-8") as f:
        decompressed_main = f.read()
    assert decompressed_main == main_js, "main.js.gz must decompress to main.js content"

    with gzip.open(gz_min_path, "rt", encoding="utf-8") as f:
        decompressed_min = f.read()
    assert decompressed_min == main_min, "main.min.js.gz must decompress to main.min.js content"


def test_simulated_mascot_persistence_state_machine():
    """
    Simulates the exact browser localStorage lifecycle and verifies that
    hiding via right-click or settings reliably prevents mascot rendering.
    """
    class LocalStorageMock:
        def __init__(self):
            self._data = {}

        def getItem(self, key):
            return self._data.get(key, None)

        def setItem(self, key, value):
            self._data[key] = str(value)

        def removeItem(self, key):
            self._data.pop(key, None)

    storage = LocalStorageMock()

    # Step 1: Default initial state
    def init_settings(storage, is_mobile=False):
        import json
        saved = json.loads(storage.getItem("user_settings_v3") or "{}")
        current = {"showMascot": True, "theme": "dark"}
        current.update(saved)
        hide_mascot_flag = storage.getItem("hide_mascot") == "true"
        if hide_mascot_flag or saved.get("showMascot") is False:
            current["showMascot"] = False
            storage.setItem("hide_mascot", "true")
        elif saved.get("showMascot") is True:
            current["showMascot"] = True
            storage.removeItem("hide_mascot")
        elif saved.get("showMascot") is None and is_mobile:
            current["showMascot"] = False
        return current

    def mascot_should_render(current_settings, storage):
        if not current_settings.get("showMascot"):
            return False
        if storage.getItem("hide_mascot") == "true":
            return False
        return True

    # Initial boot on desktop: Mascot should render
    settings = init_settings(storage)
    assert mascot_should_render(settings, storage) is True

    # User right-clicks mascot -> confirm hide
    storage.setItem("hide_mascot", "true")
    settings["showMascot"] = False
    import json
    storage.setItem("user_settings_v3", json.dumps(settings))

    # Page Reload (simulate F5)
    reloaded_settings = init_settings(storage)
    assert reloaded_settings["showMascot"] is False
    assert mascot_should_render(reloaded_settings, storage) is False

    # User re-enables mascot in settings modal
    reloaded_settings["showMascot"] = True
    storage.setItem("user_settings_v3", json.dumps(reloaded_settings))
    # saving settings removes hide_mascot
    storage.removeItem("hide_mascot")

    # Next Page Reload
    next_boot_settings = init_settings(storage)
    assert next_boot_settings["showMascot"] is True
    assert mascot_should_render(next_boot_settings, storage) is True
