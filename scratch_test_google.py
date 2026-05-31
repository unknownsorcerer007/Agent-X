import os
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from cli import get_token
from src.core.llm_provider import auto_detect_provider, get_llm

async def main():
    # Force the first API key
    os.environ["GOOGLE_API_KEY"] = "AIzaSyCWrgHdSvdoE8617uHVU8JS9czi7F0zETM"
    
    # Enable logging for detail
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    provider_config = auto_detect_provider()
    print("Auto-detected Provider config:", provider_config)
    if not provider_config:
        print("No provider detected!")
        return

    # Check if google is the provider
    llm = get_llm()
    print("Active provider in LLM class:", llm.provider_name)
    print("Base URL:", llm.base_url)
    print("Model:", llm.model)
    
    # Try calling complete
    try:
        response = await llm.complete(
            prompt="Hello, return JSON: {\"action\": \"reply\", \"message\": \"test\"}",
            system="You must respond only in JSON",
            response_format={"type": "json_object"}
        )
        print("Response received:")
        print(response)
    except Exception as e:
        print("Exception caught:", e)

if __name__ == '__main__':
    asyncio.run(main())
