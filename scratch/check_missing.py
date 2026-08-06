import ast
import os

def get_node_text(content, node):
    lines = content.split('\n')
    return '\n'.join(lines[node.lineno-1:node.end_lineno])

def main():
    target = r"C:\Users\danat\Desktop\dvachbot\main.py"
    with open(target, "r", encoding="utf-8") as f:
        content = f.read()
        
    tree = ast.parse(content)
    
    names_to_extract = {
        "ANIME_CMD_COOLDOWN_PHRASES",
        "ANIME_CMD_SEARCHING_PHRASES",
        "ANIME_CMD_SUCCESS_PHRASES",
        "HAS_WORDCLOUD",
        "INVITE_TEXTS",
        "INVITE_TEXTS_EN",
        "INVITE_TEXTS_JP",
        "ROULETTE_COOLDOWN_PHRASES",
        "ROULETTE_RESULT_PHRASES",
        "WebAppInfo",
        "WordCloud",
        "_prepare_anime_content",
        "_safe_delete_user_message",
        "detect_media_type",
        "generate_deanon_info",
        "get_author_id_by_reply",
        "get_help_keyboard",
        "git_commit_and_push_db",
        "process_shadow_reject",
        "send_moderation_notice"
    }
    
    found_names = set()
    
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in names_to_extract:
                found_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in names_to_extract:
                    found_names.add(t.id)
                    
    missing = names_to_extract - found_names
    print(f"Found: {found_names}")
    print(f"Missing: {missing}")

if __name__ == "__main__":
    main()
