def fix_network_test():
    with open('network_test.py', 'r') as f:
        content = f.read()
    content = content.replace('from verification_scripts.common.secret_redaction import redact_secrets', 'from common.secret_redaction import redact_secrets')
    with open('network_test.py', 'w') as f:
        f.write(content)
fix_network_test()
