#!/usr/bin/env python3
import urllib.request
import urllib.error
import json
import os
import sys
import asyncio
from pathlib import Path

# Add project root to sys.path to allow imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.core.llm_provider import auto_detect_provider, get_llm

def get_token():
    token = ""
    env_path = os.path.join(project_root, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    os.environ[key] = val
                    if key == "AGENT_TOKEN":
                        token = val
    return token

async def send_command_to_server(command: str, params: dict, token: str):
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

    import time
    max_retries = 5
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode())
        except urllib.error.URLError as e:
            if hasattr(e, 'reason') and isinstance(e.reason, ConnectionRefusedError):
                if attempt < max_retries - 1:
                    time.sleep(3)
                else:
                    return {"status": "error", "error": "Server is not running. Start server first."}
            elif hasattr(e, 'read'):
                try:
                    return json.loads(e.read().decode())
                except Exception:
                    return {"status": "error", "error": e.read().decode()}
            else:
                return {"status": "error", "error": str(e.reason)}

async def agent_loop():
    token = get_token()
    print("=========================================")
    print("      Agent-X Interactive CLI (Smart)    ")
    print("=========================================")
    
    provider_config = auto_detect_provider()
    if not provider_config:
        print("[!] No LLM Provider found in .env (e.g., OPENAI_API_KEY).")
        print("[!] Falling back to basic command mode.\n")
        llm = None
    else:
        print(f"[*] AI Reasoning Engine Enabled: {provider_config['provider']} ({provider_config['model']})")
        print("[*] I will understand and plan your requests before acting.\n")
        llm = get_llm()

    print("Type 'exit' to quit.\n")

    while True:
        try:
            user_input = input("Agent-X > ").strip()
            if user_input.lower() in ["exit", "quit"]:
                break
            if not user_input:
                continue

            if llm is None:
                # Basic fallback
                url = user_input.lower().replace("visit ", "").replace("go to ", "").strip()
                if not url.startswith("http"):
                    url = f"https://{url}"
                    if "." not in url:
                        url = f"{url}.com"
                
                print(f"[*] Sending smart-navigate to: {url} ...")
                result = await send_command_to_server("smart-navigate", {"url": url}, token)
                print(f"[{result.get('status', 'Error')}]")
                if 'data' in result:
                    print(json.dumps(result['data'], indent=2))
                continue

            # Smart ReAct Loop
            system_prompt = """You are Agent-X, a powerful browser automation AI.
You have access to a real browser. You can execute actions by returning JSON.
Your goal is to complete the user's request. If it requires multiple steps, do them one by one.

Available commands:
1. smart-navigate: {"action": "execute", "command": "smart-navigate", "params": {"url": "https://..."}}
2. smart-find: {"action": "execute", "command": "smart-find", "params": {"query": "Search query or element description"}}
3. click: {"action": "execute", "command": "click", "params": {"selector": "..."}}
4. type: {"action": "execute", "command": "type", "params": {"selector": "...", "text": "..."}}
5. get-text: {"action": "execute", "command": "get-text", "params": {"selector": "body"}}
6. reply: {"action": "reply", "message": "Final answer to the user"}

You must return ONLY valid JSON matching this schema:
{"action": "execute" | "reply", "command"?: string, "params"?: dict, "message"?: string}

Think step-by-step before returning the JSON. If the user asks to generate an image, first use smart-navigate to go to a free image generator (like craiyon.com or huggingface.co), then use smart-find and type/click to generate it.
"""
            
            messages = [{"role": "user", "content": user_input}]
            
            print("[*] Thinking...")
            
            while True:
                response = await llm.complete(
                    prompt=messages[-1]["content"],
                    system=system_prompt,
                    history=messages[:-1],
                    response_format={"type": "json_object"}
                )
                
                if response["status"] != "success":
                    print(f"[Error] AI failed to respond: {response.get('error')}")
                    break
                    
                content = response["content"]
                try:
                    action_data = json.loads(content)
                except Exception as e:
                    print(f"[Error] AI returned invalid JSON: {content}")
                    break
                    
                action = action_data.get("action")
                
                if action == "reply":
                    print(f"\n[Agent-X] {action_data.get('message')}\n")
                    break
                    
                elif action == "execute":
                    cmd = action_data.get("command")
                    params = action_data.get("params", {})
                    print(f"[*] Executing: {cmd} with {params}")
                    
                    result = await send_command_to_server(cmd, params, token)
                    if result.get("status") == "success":
                        result_msg = f"Command {cmd} succeeded. Data: {json.dumps(result.get('data', {}))}"
                    else:
                        result_msg = f"Command {cmd} failed. Error: {result.get('error')}"
                        
                    print(f"   -> {result_msg[:200]}...")
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": f"System execution result:\n{result_msg}\nWhat's next? Return JSON."})
                else:
                    print(f"[Error] Unknown action type: {action}")
                    break

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[Fatal Error] {e}")

    print("\nGoodbye!")

if __name__ == "__main__":
    asyncio.run(agent_loop())
