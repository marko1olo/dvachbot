import re

with open('site_tgach/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace templates.TemplateResponse("something.jinja2", {
# with templates.TemplateResponse(request=request, name="something.jinja2", context={
# Regex: templates\.TemplateResponse\(\s*("([^"]+\.jinja2)")\s*,\s*(\{.*?)
# Wait, the `{` might be on the same line or next line.
# A simpler approach: replace templates.TemplateResponse(" with templates.TemplateResponse(request=request, name="
# and then replace , { with , context={
# Since it's Python, let's just use re.sub.

def replacer(match):
    name_arg = match.group(1) # e.g. "index.jinja2"
    rest = match.group(2) # e.g. , { ... }
    
    # Check if request= is already there
    if 'request=' in name_arg:
        return match.group(0)
        
    # We will just rewrite it to explicitly pass request=request, name=..., context=...
    # But wait, what if `request` is not named `request` in that scope?
    # Usually in FastAPI route handlers it's called `request`.
    # Let's hope it's always `request: Request`. If not, we could extract `request` from context dict, but it's easier to just pass request=request.
    
    return f'templates.TemplateResponse(request=request, name={name_arg}{rest}'

# Match templates.TemplateResponse("filename.jinja2",
pattern = re.compile(r'templates\.TemplateResponse\(\s*("[^"]+\.jinja2")(\s*,)')
content = pattern.sub(replacer, content)

# Now replace the context arg.
# Actually, the signature is TemplateResponse(request, name, context, ...).
# If we change it to TemplateResponse(request=request, name="file.jinja2", context={...}) it's better.
# Let's do it simply:
# Just replace `templates.TemplateResponse("` with `templates.TemplateResponse(request=request, name="`
# Wait, some calls might have status_code as 3rd positional argument? No, the traceback showed they used kwargs for status_code or passed a dict as 2nd arg.
# We can just change the first argument to be explicit kwargs for `request` and `name`.
# Then we need to replace the second argument (the dict) with `context=...` to be safe, but actually, if we provide kwargs before positional args, Python will complain!
# Ah! If we do `TemplateResponse(request=request, name="index.jinja2", {...})`, Python throws "positional argument follows keyword argument".
# So we MUST change the dict to `context={...}`.

# Let's use a more robust regex.
def full_replacer(match):
    name_str = match.group(1)
    dict_start = match.group(2)
    return f'templates.TemplateResponse(request=request, name={name_str}, context={dict_start}'

pattern2 = re.compile(r'templates\.TemplateResponse\(\s*("[^"]+\.jinja2")\s*,\s*(\{)')
content = pattern2.sub(full_replacer, content)

with open('site_tgach/main.py', 'w', encoding='utf-8') as f:
    f.write(content)
