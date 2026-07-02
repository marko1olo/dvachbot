import re
import sys

def main(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Regex to find window.formatTextGlobal and add unclosed tags fix
    match = re.search(r'(window\.formatTextGlobal = \(text, opId = null, boardId = null, threadId = null\) => {.*?)(return s;\n};)', content, re.DOTALL)
    if match:
        func_body = match.group(1)
        return_stmt = match.group(2)

        # Check if the fix is already present
        if 'function closeUnclosedTags' in func_body:
            print(f"Fix already present in {filepath}")
            return

        print(f"Applying fix to {filepath}")

        # Define the fix logic to add before the return statement
        fix_code = """
    function closeUnclosedTags(html) {
        const div = document.createElement('div');
        div.innerHTML = html;
        return div.innerHTML;
    }
    s = closeUnclosedTags(s);

    """

        new_content = content[:match.end(1)] + fix_code + content[match.start(2):]

        with open(filepath, 'w') as f:
            f.write(new_content)
    else:
        print(f"Could not find window.formatTextGlobal function in {filepath}")

if __name__ == '__main__':
    main('site_tgach/static/js/main.js')
    main('Dubsite_tgach/static/js/main.js')
