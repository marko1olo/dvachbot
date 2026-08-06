import py_compile
import compileall
import ast
import os
import sys
import traceback

workspace = r"C:\Users\danat\Desktop\dvachbot"
os.chdir(workspace)
sys.path.insert(0, workspace)

target_files = [
    "user_manager.py",
    "periodic_publisher.py",
    "broadcaster.py",
    "delivery_manager.py",
    "post_processor.py",
    "economy_extension.py",
    "admin_manager.py",
    "handlers/message_router.py",
    "site_tgach/importer.py",
    "site_tgach/mirror_worker.py",
    "site_tgach/main.py",
    "Dubsite_tgach/main.py",
    "main.py",
]

print("=== STEP 1: py_compile individual files ===")
py_compile_errors = []
for rel_path in target_files:
    full_path = os.path.join(workspace, rel_path)
    if not os.path.exists(full_path):
        print(f"[-] FILE NOT FOUND: {rel_path}")
        py_compile_errors.append((rel_path, "File not found"))
        continue
    try:
        py_compile.compile(full_path, doraise=True)
        print(f"[+] OK py_compile: {rel_path}")
    except py_compile.PyCompileError as e:
        print(f"[!] FAIL py_compile: {rel_path}: {e}")
        py_compile_errors.append((rel_path, str(e)))
    except Exception as e:
        print(f"[!] FAIL py_compile (other exception): {rel_path}: {e}")
        py_compile_errors.append((rel_path, str(e)))

print("\n=== STEP 2: compileall workspace ===")
compileall_success = False
try:
    # quiet=0 to get visible output if needed, or quiet=1
    res = compileall.compile_dir(workspace, maxlevels=5, quiet=0)
    print(f"[+] compileall result: {res}")
    compileall_success = res
except Exception as e:
        print(f"[!] compileall exception: {e}")
        compileall_success = False

print("\n=== STEP 3: Detailed AST Inspection ===")
ast_issues = []
for rel_path in target_files:
    full_path = os.path.join(workspace, rel_path)
    if not os.path.exists(full_path):
        continue
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=rel_path)
        
        # Check AST nodes
        class ASTVisitor(ast.NodeVisitor):
            def __init__(self, filename):
                self.filename = filename
                self.except_blocks = 0
                self.bare_excepts = 0
                self.empty_excepts = 0

            def visit_ExceptHandler(self, node):
                self.except_blocks += 1
                if node.type is None:
                    self.bare_excepts += 1
                # Check body of except handler
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    self.empty_excepts += 1
                self.generic_visit(node)

        visitor = ASTVisitor(rel_path)
        visitor.visit(tree)
        print(f"[+] AST Parsed {rel_path}: {visitor.except_blocks} except blocks ({visitor.bare_excepts} bare, {visitor.empty_excepts} empty pass)")

    except SyntaxError as e:
        print(f"[!] AST SyntaxError in {rel_path}: line {e.lineno}, col {e.offset}: {e.msg}")
        ast_issues.append((rel_path, f"SyntaxError line {e.lineno}: {e.msg}"))
    except Exception as e:
        print(f"[!] AST exception in {rel_path}: {e}")
        ast_issues.append((rel_path, str(e)))

print("\n=== SUMMARY ===")
print(f"py_compile errors: {len(py_compile_errors)}")
print(f"compileall success: {compileall_success}")
print(f"AST issues: {len(ast_issues)}")

if py_compile_errors or not compileall_success or ast_issues:
    print("VERDICT: REQUEST_CHANGES")
else:
    print("VERDICT: APPROVE")
