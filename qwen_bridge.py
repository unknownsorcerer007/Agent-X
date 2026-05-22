#!/usr/bin/env python3
"""
Agent-OS Qwen Bridge
Connects Qwen AI to Agent-OS browser — Qwen can now browse the web.

Usage:
    # 1. Start Agent-OS
    python main.py --agent-token "qwen-agent"

    # 2. Run this bridge (in another terminal)
    DASHSCOPE_API_KEY="<YOUR_DASHSCOPE_KEY>" python qwen_bridge.py

    # 3. Chat with Qwen and it can browse!

    # Or use a different model:
    DASHSCOPE_API_KEY="<YOUR_DASHSCOPE_KEY>" python qwen_bridge.py --model qwen-max

Environment:
    DASHSCOPE_API_KEY  — Your DashScope API key (from https://dashscope.console.aliyun.com/)
    AGENT_OS_URL       — Agent-OS endpoint (default: http://localhost:8001)
    AGENT_OS_TOKEN     — Agent token (default: qwen-agent)
"""
import os
import sys
import json
import asyncio
import argparse
import httpx

# ─── Configuration ───────────────────────────────────────────

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
AGENT_OS_URL = os.environ.get("AGENT_OS_URL", "http://localhost:8001")
AGENT_OS_TOKEN = os.environ.get("AGENT_OS_TOKEN", "qwen-agent")

# China endpoint (change to dashscope-intl.aliyuncs.com for international)
BASE_URL = os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

# ─── Agent-OS Tools (OpenAI format for Qwen) ────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate to a URL. Anti-detection built-in to bypass CAPTCHAs and bot protection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click an element on the page using CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector for the element"}
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "Type text into the currently focused element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill_form",
            "description": "Fill form fields. Keys are CSS selectors, values are the text to fill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fields": {
                        "type": "object",
                        "description": "Dictionary of {selector: value} pairs",
                        "additionalProperties": {"type": "string"}
                    }
                },
                "required": ["fields"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_get_content",
            "description": "Get the current page's text content and URL.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_get_links",
            "description": "Get all links on the current page.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Take a screenshot of the current page.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_evaluate_js",
            "description": "Execute JavaScript in the page context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {"type": "string", "description": "JavaScript code to execute"}
                },
                "required": ["script"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "Scroll the page up or down.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"], "default": "down"},
                    "amount": {"type": "integer", "default": 500}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_press",
            "description": "Press a keyboard key (Enter, Tab, Escape, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key name (Enter, Tab, Escape, Backspace)"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_back",
            "description": "Go back in browser history.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_wait",
            "description": "Wait for an element to appear on the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "timeout": {"type": "integer", "default": 10000}
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scan_xss",
            "description": "Scan a URL for XSS vulnerabilities.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scan_sensitive",
            "description": "Scan the current page for exposed sensitive data (API keys, tokens, passwords).",
            "parameters": {"type": "object", "properties": {}}
        }
    },
]

# ─── Agent-OS API Client ─────────────────────────────────────

async def agent_os_command(command: str, params: dict = None) -> dict:
    """Send a command to Agent-OS and get the result."""
    data = {"token": AGENT_OS_TOKEN, "command": command}
    if params:
        data.update(params)

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.post(f"{AGENT_OS_URL}/command", json=data)
            result = response.json()

            # Truncate huge responses (screenshots, long HTML)
            if "screenshot" in result and len(result["screenshot"]) > 100:
                result["screenshot"] = f"[Screenshot: {len(result['screenshot'])} bytes base64]"
            if "html" in result and len(result["html"]) > 3000:
                result["html"] = result["html"][:3000] + "... [truncated]"
            if "text" in result and len(result["text"]) > 3000:
                result["text"] = result["text"][:3000] + "... [truncated]"

            return result
        except httpx.ConnectError:
            return {"status": "error", "error": f"Cannot connect to Agent-OS at {AGENT_OS_URL}. Is it running?"}
        except Exception as e:
            return {"status": "error", "error": str(e)}


async def execute_tool(tool_name: str, arguments: dict) -> str:
    """Map tool name to Agent-OS command and execute it."""
    command_map = {
        "browser_navigate": "navigate",
        "browser_click": "click",
        "browser_type": "type",
        "browser_fill_form": "fill-form",
        "browser_get_content": "get-content",
        "browser_get_links": "get-links",
        "browser_screenshot": "screenshot",
        "browser_evaluate_js": "evaluate-js",
        "browser_scroll": "scroll",
        "browser_press": "press",
        "browser_back": "back",
        "browser_wait": "wait",
        "browser_scan_xss": "scan-xss",
        "browser_scan_sensitive": "scan-sensitive",
    }

    command = command_map.get(tool_name)
    if not command:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    print(f"  🔧 Executing: {tool_name}({json.dumps(arguments)[:100]})")
    result = await agent_os_command(command, arguments)
    return json.dumps(result, indent=2)


# ─── Qwen API Client ─────────────────────────────────────────

async def chat_with_qwen(model: str, messages: list) -> dict:
    """Send a chat request to Qwen API."""
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.7,
        "max_tokens": 4096,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )

        if response.status_code != 200:
            return {"error": f"API error {response.status_code}: {response.text[:500]}"}

        return response.json()


# ─── Main Chat Loop ──────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Agent-OS Qwen Bridge")
    parser.add_argument("--model", default="qwen-plus", help="Qwen model to use")
    parser.add_argument("--system", default=None, help="System prompt override")
    args = parser.parse_args()

    if not DASHSCOPE_API_KEY:
        print("❌ DASHSCOPE_API_KEY not set!")
        print("   Get your key from: https://dashscope.console.aliyun.com/")
        print("   Then run: export DASHSCOPE_API_KEY='<YOUR_KEY>'")
        sys.exit(1)

    # Check Agent-OS is running
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{AGENT_OS_URL}/status")
            status = resp.json()
            print(f"✅ Agent-OS connected: {status.get('version', 'unknown')} | {len(TOOLS)} tools available")
    except:
        print(f"❌ Cannot connect to Agent-OS at {AGENT_OS_URL}")
        print("   Start it with: python main.py --agent-token 'qwen-agent'")
        sys.exit(1)

    system_prompt = args.system or """You are a helpful AI assistant with access to a web browser. You can:
- Navigate to any website (navigate)
- Click elements, type text, fill forms (click, type, fill_form)
- Read page content and links (get_content, get_links)
- Take screenshots (screenshot)
- Execute JavaScript (evaluate_js)
- Scan for vulnerabilities (scan_xss, scan_sensitive)
- Scroll, press keys, go back, wait for elements

When the user asks you to do something on the web, use the browser tools to accomplish it.
Always tell the user what you found or what you did on the page.
Be concise and helpful. Use the browser actively — don't just talk about what you could do."""

    messages = [{"role": "system", "content": system_prompt}]

    print(f"\n🤖 Qwen ({args.model}) + Agent-OS Browser")
    print("=" * 50)
    print("Type your message. The AI can browse the web!")
    print("Commands: /clear (reset chat), /quit (exit)")
    print("=" * 50)

    while True:
        try:
            user_input = input("\n👤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye! 👋")
            break

        if not user_input:
            continue

        if user_input == "/quit":
            print("Bye! 👋")
            break

        if user_input == "/clear":
            messages = [{"role": "system", "content": system_prompt}]
            print("🗑️ Chat cleared.")
            continue

        messages.append({"role": "user", "content": user_input})

        # Agent loop: keep calling Qwen until no more tool calls
        max_iterations = 10
        for iteration in range(max_iterations):
            print(f"\n🧠 Thinking..." if iteration == 0 else f"🔧 Using browser (step {iteration + 1})...")

            response = await chat_with_qwen(args.model, messages)

            if "error" in response:
                print(f"❌ Error: {response['error']}")
                messages.pop()  # Remove failed user message
                break

            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})

            # Add assistant message to history
            messages.append(message)

            # Check if there are tool calls
            tool_calls = message.get("tool_calls", [])

            if not tool_calls:
                # No tool calls — just text response
                content = message.get("content", "")
                if content:
                    print(f"\n🤖 Qwen: {content}")
                break

            # Execute each tool call
            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                tool_args = json.loads(tool_call["function"]["arguments"])
                tool_id = tool_call["id"]

                result = await execute_tool(tool_name, tool_args)

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": result,
                })

            # Check if we should stop (no more tool calls expected)
            if choice.get("finish_reason") == "stop" and not tool_calls:
                break

        else:
            print("⚠️ Max iterations reached. Starting fresh.")


if __name__ == "__main__":
    asyncio.run(main())
