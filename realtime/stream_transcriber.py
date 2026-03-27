# realtime/stream_transcriber.py
"""
StreamTranscriber — transcribes WAV chunks via Deepgram REST API.

NO Deepgram SDK used. Uses plain requests HTTP calls — works with
any deepgram-sdk version installed (or none at all).
"""

import os
import sys
import time
import requests
from pathlib import Path

# Load .env so DEEPGRAM_API_KEY is available
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")
except Exception:
    pass

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

DEEPGRAM_URL = (
    "https://api.deepgram.com/v1/listen"
    "?model=nova-2&punctuate=true&diarize=true&utterances=true"
)


def _format_utterances(utterances: list) -> str:
    speaker_map = {}
    lines = []
    for u in utterances:
        spk = u.get("speaker", 0)
        if spk not in speaker_map:
            speaker_map[spk] = "Agent" if len(speaker_map) == 0 else "Customer"
        text = u.get("transcript", "").strip()
        if text:
            lines.append(f"{speaker_map[spk]}: {text}")
    return "\n".join(lines)


def _transcribe_wav(wav_path: str, retries: int = 2) -> str:
    """POST a WAV file to Deepgram REST and return the transcript text."""

    if not DEEPGRAM_API_KEY:
        print("  [StreamTranscriber] DEEPGRAM_API_KEY not set in config/.env")
        return ""

    if not os.path.exists(wav_path):
        print(f"  [StreamTranscriber] WAV file not found: {wav_path}")
        return ""

    # Check file has actual audio data (>1 KB)
    if os.path.getsize(wav_path) < 1024:
        print("  [StreamTranscriber] WAV chunk too small — skipping")
        return ""

    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type":  "audio/wav",
    }

    for attempt in range(1, retries + 1):
        try:
            with open(wav_path, "rb") as f:
                resp = requests.post(
                    DEEPGRAM_URL,
                    headers=headers,
                    data=f,
                    timeout=60,
                )

            if resp.status_code != 200:
                print(f"  [StreamTranscriber] HTTP {resp.status_code} "
                      f"on attempt {attempt}: {resp.text[:100]}")
                time.sleep(2 * attempt)
                continue

            data = resp.json()

            # Prefer diarized utterances (gives Agent/Customer labels)
            utterances = data.get("results", {}).get("utterances")
            if utterances:
                return _format_utterances(utterances)

            # Fallback: plain transcript from first channel
            try:
                return (data["results"]["channels"][0]
                            ["alternatives"][0]["transcript"])
            except (KeyError, IndexError):
                return ""

        except requests.exceptions.Timeout:
            print(f"  [StreamTranscriber] Timeout on attempt {attempt}")
            time.sleep(3 * attempt)

        except requests.exceptions.ConnectionError as e:
            print(f"  [StreamTranscriber] Connection error: {e}")
            time.sleep(2 * attempt)

        except Exception as e:
            print(f"  [StreamTranscriber] Unexpected error: {e}")
            time.sleep(2)

    return ""


class StreamTranscriber:
    """
    Accumulates a rolling transcript from successive WAV chunks.

    How to use:
        t = StreamTranscriber(on_transcript_callback=fn)
        t.reset()                        # call before each new session
        t.transcribe_chunk(wav_path)     # call per audio chunk
        text = t.get_transcript()        # get full text so far
    """

    def __init__(self, on_transcript_callback=None):
        self.callback        = on_transcript_callback
        self.full_transcript = ""
        self.chunk_count     = 0
        print("  [StreamTranscriber] Ready — using Deepgram REST (nova-2)")

    def reset(self):
        self.full_transcript = ""
        self.chunk_count     = 0
        print("  [StreamTranscriber] Reset")

    def transcribe_chunk(self, wav_path: str) -> str:
        new_text = _transcribe_wav(wav_path)

        if new_text and new_text.strip():
            self.chunk_count += 1
            sep = "\n" if self.full_transcript else ""
            self.full_transcript += sep + new_text.strip()
            print(f"  [StreamTranscriber] Chunk {self.chunk_count}: "
                  f"+{len(new_text)} chars | total={len(self.full_transcript)}")

            if self.callback:
                try:
                    self.callback(new_text, self.full_transcript)
                except Exception as e:
                    print(f"  [StreamTranscriber] Callback error: {e}")
        else:
            print(f"  [StreamTranscriber] Chunk returned empty (silence?)")

        return new_text

    def get_transcript(self) -> str:
        return self.full_transcript