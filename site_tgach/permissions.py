from site_tgach.admin_config import ADMIN_IDS

ROLE_HIERARCHY = {
    'user': 0,     # Обычный анон (постинг)
    'janitor': 1,  # Дворник (удаление постов, закрытие репортов)
    'mod': 2,      # Модератор (баны, теневые баны, закреп тредов)
    'admin': 3     # Админ (вайп, смена ролей, настройки, полный доступ)
}

def check_perm(user: dict, required_role: str) -> bool:
    """
    Проверяет, достаточно ли прав у пользователя для действия.
    Возвращает True/False.
    """
    if not user:
        return False
    if user.get('id') in ADMIN_IDS:
        return True
    user_role = user.get('role', 'user')
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    req_level = ROLE_HIERARCHY.get(required_role, 0)
    return user_level >= req_level
