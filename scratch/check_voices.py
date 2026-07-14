import asyncio
import edge_tts

async def main():
    try:
        text = "Xin chào"
        voice = "vi-VN-HoaiMyNeural"
        communicate = edge_tts.Communicate(text=text, voice=voice)
        await communicate.save("scratch/test_vi.mp3")
        print("Successfully synthesized test_vi.mp3!")
    except Exception as e:
        print("Error synthesizing:", e)

if __name__ == "__main__":
    asyncio.run(main())
