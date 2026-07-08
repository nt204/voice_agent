import asyncio
from google import genai
from google.genai import types

async def main():
    try:
        # Dummy test to inspect exceptions when sending client_content without turns
        # We don't have API key but we can mock or see if it throws a type error immediately
        pass
    except Exception as e:
        print(e)

asyncio.run(main())
