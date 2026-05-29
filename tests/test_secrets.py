import os
import re

def test_no_secrets_in_code():
    """Verify that no hardcoded credentials or API keys exist in Python files."""
    pattern = re.compile(r'(api[_-]?key|password|secret|token)\s*=\s*[\"\'][^\"\']{20,}[\"\']', re.IGNORECASE)
    found_secrets = []

    for root, dirs, files in os.walk('.'):
        # Prune folders
        dirs[:] = [d for d in dirs if d not in ('venv', '__pycache__', '.git')]
        for file in files:
            if file.endswith('.py') and file != 'test_secrets.py':
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_no, line in enumerate(f, 1):
                            if pattern.search(line):
                                found_secrets.append(f"{path}:{line_no} : {line.strip()}")
                except Exception as e:
                    print(f"Error reading {path}: {e}")

    assert not found_secrets, f"Possible secrets found:\n" + "\n".join(found_secrets)

if __name__ == "__main__":
    test_no_secrets_in_code()
    print("Secret scan complete")
