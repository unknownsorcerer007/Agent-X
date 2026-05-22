import re

# 1. READ stealth_god.py
with open("src/core/stealth_god.py", "r", encoding="utf-8") as f:
    god_content = f.read()

# Extract ConsistentFingerprint class (between imports and generate_god_mode_js)
fp_match = re.search(r"(@dataclass\nclass ConsistentFingerprint:.*?)# ═══════════════════════════════════════════════════════════════\n# GOD MODE JAVASCRIPT", god_content, re.DOTALL)
if fp_match:
    consistent_fp_code = fp_match.group(1)
else:
    print("Could not find ConsistentFingerprint in stealth_god.py")
    exit(1)

# Remove it from stealth_god.py
god_content = god_content.replace(consistent_fp_code, "from src.security.evasion_engine import ConsistentFingerprint\n\n")

# Write stealth_god.py back
with open("src/core/stealth_god.py", "w", encoding="utf-8") as f:
    f.write(god_content)
print("Updated stealth_god.py")


# 2. READ evasion_engine.py
with open("src/security/evasion_engine.py", "r", encoding="utf-8") as f:
    evasion_content = f.read()

# Add dataclass import if not present
if "from dataclasses import dataclass" not in evasion_content:
    evasion_content = evasion_content.replace("from typing import Optional, Dict, Any", "from typing import Optional, Dict, Any\nfrom dataclasses import dataclass")

# Replace generate_fingerprint and build_fingerprint_injection_js
# Find the start of WINDOWS_WEBGL_RENDERERS
start_idx = evasion_content.find("WINDOWS_WEBGL_RENDERERS = [")
# Find the start of CLOUDSCRAPER INTEGRATION
end_idx = evasion_content.find("# CLOUDSCRAPER INTEGRATION")

if start_idx != -1 and end_idx != -1:
    old_fingerprint_code = evasion_content[start_idx:end_idx]
    
    # We replace it with ConsistentFingerprint code
    replacement = consistent_fp_code + "\n\n"
    
    evasion_content = evasion_content.replace(old_fingerprint_code, replacement)
else:
    print("Could not find the fingerprint section in evasion_engine.py")

# Update EvasionEngine generate_fingerprint call
evasion_content = evasion_content.replace("fp = generate_fingerprint(os_target=os_target)", "fp = ConsistentFingerprint().to_dict()")

# Remove get_injection_js and inject_into_page from EvasionEngine
evasion_content = re.sub(r"    def get_injection_js.*?(?=    def get_fingerprint)", "", evasion_content, flags=re.DOTALL)

# Write evasion_engine.py back
with open("src/security/evasion_engine.py", "w", encoding="utf-8") as f:
    f.write(evasion_content)
print("Updated evasion_engine.py")

