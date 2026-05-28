#!/usr/bin/env python3
import urllib.request
import urllib.error
import json
import os
import sys

# Try to load token from .env
token = ""
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            if line.startswith("AGENT_TOKEN="):
                token = line.strip().split("=")[1].strip('"').strip("'")

print("=========================================")
print("          Agent-X Interactive CLI        ")
print("=========================================")
print("Type 'exit' to quit.\n")



while True:
    try:
        user_input = input("Agent-X > ")
        if user_input.lower() in ["exit", "quit"]:
            break
        
        if not user_input.strip():
            continue

        # Basic parsing to handle natural language like "visit reddit"
        url = user_input.lower().replace("visit ", "").replace("go to ", "").strip()
        if not url.startswith("http"):
            url = f"https://{url}"
            # If they just typed 'reddit' instead of 'reddit.com'
            if "." not in url:
                url = f"{url}.com"

        command = "smart-navigate"
        params = {"url": url}
        print(f"[*] Sending command to navigate to: {url} ...")

        payload = json.dumps({
            "command": command,
            "params": params,
            "token": token
        }).encode('utf-8')

        req = urllib.request.Request(
            "http://localhost:8001/command",
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode())
                print(f"[Success] {result.get('status', 'OK')}")
                if 'data' in result:
                    print(json.dumps(result['data'], indent=2))
        except urllib.error.URLError as e:
            if hasattr(e, 'read'):
                err_response = e.read().decode()
                print(f"[Error] {e.reason}: {err_response}")
            else:
                print(f"[Error] {e.reason} - Is the Agent-X server running on port 8001?")

    except KeyboardInterrupt:
        break

print("\nGoodbye!")
