with open('Dubsite_tgach/importer.py', 'r') as f:
    content = f.read()

content = content.replace(
    "non_op_task_ids = list({row[1] for row in rows if not row[8]})",
    "non_op_task_ids = list({row[1] for row in rows if not row[8]})"
)

# No changes needed for indices, they are exactly 1 and 8 as verified.
