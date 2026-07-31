import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scratch.dump_format2 import format_post_text

def test():
    assert format_post_text("hello <script>") == "hello &lt;scrlpt&gt;"
    assert format_post_text(">greentext") == '<span class="greentext">&gt;greentext</span>'
    assert format_post_text("[b]bold[/b]") == "<b>bold</b>"

test()
print("test passed")
