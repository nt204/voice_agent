import asyncio
from google import genai
from google.genai import types

async def main():
    client = genai.Client(api_key="TEST")
    # Instead of full connect which requires network and auth, just see if constructing 
    # the request dict crashes.
    try:
        from google.genai._common import t
        from google.genai.live import live_converters
        
        turns = None
        turn_complete = False
        client_content = t.t_client_content(turns, turn_complete).model_dump(
            mode='json', exclude_none=True
        )
        client_content_dict = live_converters._LiveClientContent_to_mldev(
            from_object=client_content
        )
        print("Success:", client_content_dict)
    except Exception as e:
        print("Error:", type(e).__name__, e)

asyncio.run(main())
