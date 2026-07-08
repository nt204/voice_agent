Viber Business Calls -> Infobip -> AI backend -> Gemini Live

This project runs a Python bridge for this call path:

1. User calls your Viber Business Calls number.
2. Infobip routes the call into a Calls API dialog/conference with a `WEBSOCKET_ENDPOINT` leg.
3. Infobip opens `wss://<your-domain>/infobip/ws`.
4. This backend forwards raw PCM audio to Gemini Live.
5. Gemini Live audio is sent back to Infobip as 20 ms PCM frames.

## Important

Rotate both keys you pasted in chat before deploying. Do not commit real API keys.

Infobip must enable these on your account before this can receive real Viber calls:

- Viber Business Calls
- Dedicated Viber Voice number
- Calls API
- WebSocket endpoint / media streaming
- Inbound call routing to a Calls API application, dialog, or conference

## Run locally

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
```

Expose the server with a public HTTPS tunnel for testing:

```bash
ngrok http 3000
```

Set `PUBLIC_BASE_URL` in `.env` to the HTTPS URL from the tunnel.

## Create Infobip WebSocket endpoint config

```bash
python -m scripts.create_infobip_ws_config
```

Copy the returned `id` into:

```bash
INFOBIP_WS_CONFIG_ID=<returned-id>
```

The script creates this Infobip Calls config:

```json
{
  "type": "WEBSOCKET_ENDPOINT",
  "url": "wss://your-domain/infobip/ws?token=...",
  "sampleRate": "24000"
}
```

## Infobip portal setup

After Infobip provisions your Viber Voice number, configure inbound routing so Viber calls are connected to a Calls API dialog/conference that includes the WebSocket endpoint config ID above.

Use `/infobip/events` as your Calls API event webhook if Infobip asks for an event URL.

The bridge endpoint is:

```text
wss://<PUBLIC_BASE_URL host>/infobip/ws?token=<INFOBIP_WS_SHARED_SECRET>
```

## Notes

- Infobip WebSocket endpoint audio is Linear PCM 16-bit with 20 ms frames.
- Gemini Live accepts raw PCM audio input and returns raw PCM audio output.
- The default sample rate here is `24000`, because Gemini audio output is 24 kHz and Infobip WebSocket endpoint supports 24 kHz.

## Test that Gemini is embedded

First test Gemini Live directly:

```bash
source .venv/bin/activate
python -m scripts.test_gemini_live_text
```

Expected result:

```text
Gemini Live OK
Audio bytes received: <number greater than 0>
Transcript: ...
```

Then test the same path that Infobip will use. Start the server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
```

Create a mono PCM16 WAV file with your spoken test question. Then run:

```bash
python -m scripts.mock_infobip_ws \
  --url "ws://localhost:3000/infobip/ws?token=change_me" \
  --wav test-call.wav \
  --out gemini-response.pcm
```

If `gemini-response.pcm` has bytes and the server logs show `Gemini Live connected`, the AI bridge is working. For real Viber calls, Infobip still needs to provision Viber Business Calls and route the Viber Voice number to the WebSocket endpoint config.

## SignalWire inbound calls

SignalWire is a simpler path for a US phone number calling the AI agent. It does not use Viber; customers call a normal phone number.

Add these variables to `.env`:

```bash
SIGNALWIRE_STREAM_BEARER_TOKEN=replace_with_a_random_secret
SIGNALWIRE_STREAM_CODEC=L16@24000h
SIGNALWIRE_STREAM_SAMPLE_RATE=24000
```

Start the server:

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
```

Expose it with HTTPS:

```bash
ngrok http 3000
```

Set `PUBLIC_BASE_URL` in `.env` to the ngrok HTTPS URL, then restart uvicorn.

In SignalWire, buy a voice-capable US number and configure the number's inbound call handler:

```text
Request URL: https://<your-ngrok-domain>/signalwire/answer
Method: POST
```

The `/signalwire/answer` endpoint returns cXML that opens a bidirectional WebSocket to:

```text
wss://<your-ngrok-domain>/signalwire/ws
```

Local SignalWire WebSocket simulation:

```bash
python -m scripts.mock_signalwire_ws \
  --url "ws://localhost:3000/signalwire/ws" \
  --wav test-call.wav \
  --out gemini-response-signalwire.pcm \
  --bearer-token "replace_with_a_random_secret"
```

If `gemini-response-signalwire.pcm` has bytes and logs show `SignalWire stream started` and `Gemini Live connected`, the SignalWire -> Gemini -> SignalWire path is working.

## Telnyx inbound calls

Telnyx can replace SignalWire for a normal phone-number call into the AI agent.

Add these variables to `.env`:

```bash
TELNYX_STREAM_TOKEN=replace_with_a_random_secret
TELNYX_STREAM_CODEC=PCMU
TELNYX_STREAM_SAMPLE_RATE=8000
TELNYX_STREAM_TRACK=inbound_track
```

Start the server and expose it with HTTPS:

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
ngrok http 3000
```

Set `PUBLIC_BASE_URL` in `.env` to the ngrok HTTPS URL, then restart uvicorn.

In Telnyx, configure your TeXML app or inbound number webhook:

```text
Voice webhook URL: https://<your-ngrok-domain>/telnyx/answer
Method: POST
```

The `/telnyx/answer` endpoint returns TeXML that connects the call to a bidirectional RTP media stream:

```text
wss://<your-ngrok-domain>/telnyx/ws?token=<TELNYX_STREAM_TOKEN>
```

Local Telnyx WebSocket simulation:

```bash
python -m scripts.mock_telnyx_ws \
  --url "ws://localhost:3000/telnyx/ws?token=replace_with_a_random_secret" \
  --wav test-call.wav \
  --out gemini-response-telnyx.pcm \
  --stream-token "replace_with_a_random_secret"
```

If `gemini-response-telnyx.pcm` has bytes and logs show `Telnyx stream started` and `Gemini Live connected`, the Telnyx -> Gemini -> Telnyx path is working.

cd "/Users/macbook/Desktop/Viber call"
lsof -ti tcp:3000 | xargs kill -9
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 3000
