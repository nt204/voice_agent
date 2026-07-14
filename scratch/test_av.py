import io
import av
import edge_tts
import asyncio

async def main():
    text = "Xin chào, tôi muốn mua sữa Venus BigOne."
    communicate = edge_tts.Communicate(text=text, voice="vi-VN-HoaiMyNeural")
    mp3_data = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_data.extend(chunk["data"])
            
    print(f"Generated MP3: {len(mp3_data)} bytes")
    
    inp = av.open(io.BytesIO(bytes(mp3_data)), 'r')
    resampler = av.AudioResampler(
        format='s16',
        layout='mono',
        rate=8000,
    )
    
    pcm_out = bytearray()
    for frame in inp.decode(audio=0):
        # We need to process each frame through the resampler
        resampled_frames = resampler.resample(frame)
        if resampled_frames:
            for rf in resampled_frames:
                pcm_out.extend(rf.to_ndarray().tobytes())
                
    # Flush resampler
    flushed = resampler.resample(None)
    if flushed:
        for rf in flushed:
            pcm_out.extend(rf.to_ndarray().tobytes())
            
    print(f"Converted PCM: {len(pcm_out)} bytes, sample rate: 8000Hz mono")

if __name__ == "__main__":
    asyncio.run(main())
