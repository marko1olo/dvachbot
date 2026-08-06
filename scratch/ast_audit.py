import ast
import os
import sys

def main():
    target = r"C:\Users\danat\Desktop\dvachbot\main.py"
    with open(target, "r", encoding="utf-8") as f:
        content = f.read()
    
    tree = ast.parse(content)
    
    entities = []
    
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start_line = node.lineno
            end_line = node.end_lineno
            length = end_line - start_line + 1
            entities.append({
                "type": type(node).__name__,
                "name": node.name,
                "length": length,
                "start": start_line,
                "end": end_line
            })
            
    # Also find global dicts or lists
    globals_list = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    if isinstance(node.value, (ast.Dict, ast.List)):
                        globals_list.append(t.id)
                        
    entities.sort(key=lambda x: x["length"], reverse=True)
    
    print("Top 20 largest functions/classes:")
    for e in entities[:20]:
        print(f"{e['type']} {e['name']}: {e['length']} lines (lines {e['start']}-{e['end']})")
        
    print("\nPotential Global Dictionaries/Lists:")
    for g in globals_list:
        print(g)

if __name__ == "__main__":
    main()
