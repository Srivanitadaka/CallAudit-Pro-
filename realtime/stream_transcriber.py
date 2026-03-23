# realtime/stream_transcriber.py
"""
Stream Transcriber Module
─────────────────────────────────────────────
Transcribes audio chunks using Deepgram REST API.
Accumulates full transcript as call progresses.

Usage:
  from realtime.stream_transcriber import StreamTranscriber
  t = StreamTranscriber(on_transcript_callback=my_function)
  t.transcribe_chunk("path/to/chunk.wav")
  print(t.get_transcript())
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "config" / ".env")

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")


class StreamTranscriber:

    def __init__(self, on_transcript_callback=None):
        """
        on_transcript_callback: function(new_text, full_transcript)
        Called every time new text is transcribed.
        """
        self.callback        = on_transcript_callback
        self.full_transcript = ""
        self.chunk_count     = 0

    def transcribe_chunk(self, wav_path: str) -> str:
        """
        Transcribe a single WAV chunk using Deepgram REST API.
        Appends result to full transcript.
        Returns new text from this chunk.
        """
        if not DEEPGRAM_API_KEY:
            print("  ⚠️  DEEPGRAM_API_KEY not set in config/.env")
            return ""

        try:
            from deepgram import DeepgramClient, PrerecordedOptions

            dg = DeepgramClient(DEEPGRAM_API_KEY)

            with open(wav_path, "rb") as f:
                audio_data = f.read()

            options = PrerecordedOptions(
                model        = "nova-2",
                smart_format = True,
                language     = "en"
            )

            response = dg.listen.rest.v("1").transcribe_file(
                {"buffer": audio_data, "mimetype": "audio/wav"},
                options
            )

            text = (
                response.results
                .channels[0]
                .alternatives[0]
                .transcript
                .strip()
            )

            if text:
                self.chunk_count    += 1
                self.full_transcript += f"\n{text}"

                print(f"  📝 Chunk {self.chunk_count}: {text[:60]}...")

                if self.callback:
                    self.callback(text, self.full_transcript)

            return text

        except ImportError:
            print("  ⚠️  deepgram-sdk not installed.")
            print("     Run: pip install deepgram-sdk")
            return ""
        except Exception as e:
            print(f"  ⚠️  Transcription error: {e}")
            return ""

    def reset(self):
        """Reset transcript for new call."""
        self.full_transcript = ""
        self.chunk_count     = 0
        print("  🔄 Transcriber reset")

    def get_transcript(self) -> str:
        """Return full accumulated transcript."""
        return self.full_transcript.strip()

    def get_chunk_count(self) -> int:
        """Return number of chunks transcribed."""
        return self.chunk_count

if __name__ == "__main__":
    from pathlib import Path

    def on_transcript(new_text, full_text):
        print(f"  📝 New  : {new_text[:80]}")
        print(f"  📄 Full : {len(full_text)} chars")

    print("="*45)
    print("  Transcriber Test")
    print("="*45)

    t = StreamTranscriber(on_transcript_callback=on_transcript)

    # Find any audio file in uploads or sample_data
    test_file = None
    for folder in ["uploads", "sample_data"]:
        for ext in ["*.wav", "*.mp3", "*.m4a"]:
            files = list(Path(folder).glob(ext))
            if files:
                test_file = str(files[0])
                break
        if test_file:
            break

    if test_file:
        print(f"  File  : {test_file}")
        text = t.transcribe_chunk(test_file)
        print(f"\n  Result: {text[:200]}")
        print(f"  Chunks: {t.get_chunk_count()}")
        print("✅ Transcriber test done")
    else:
        print("  ⚠️  No audio file found")
        print("     Put a .wav or .mp3 in uploads/ folder")