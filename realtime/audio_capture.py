# realtime/audio_capture.py
"""
Audio Capture Module
─────────────────────────────────────────────
Captures microphone audio in real-time chunks.
Sends each chunk to callback for transcription.

Usage:
  from realtime.audio_capture import AudioCapture
  capture = AudioCapture(on_chunk_callback=my_function)
  capture.start()
  capture.stop()
"""

import threading
import wave
import tempfile
import os

CHUNK       = 1024
CHANNELS    = 1
RATE        = 16000
CHUNK_SECS  = 5   # send audio chunk every 5 seconds


class AudioCapture:

    def __init__(self, on_chunk_callback):
        """
        on_chunk_callback: function(wav_path)
        Called every CHUNK_SECS with path to temp WAV file.
        """
        self.callback  = on_chunk_callback
        self._running  = False
        self._thread   = None
        self._pa       = None

    def start(self):
        """Start capturing microphone audio."""
        self._running = True
        self._thread  = threading.Thread(
            target = self._capture_loop,
            daemon = True
        )
        self._thread.start()
        print("  🎤 Microphone capture started")

    def stop(self):
        """Stop capturing audio."""
        self._running = False
        if self._pa:
            try:
                self._pa.terminate()
            except Exception:
                pass
        print("  🎤 Microphone capture stopped")

    def _capture_loop(self):
        """Main capture loop — runs in background thread."""
        try:
            import pyaudio
            FORMAT = pyaudio.paInt16

            self._pa = pyaudio.PyAudio()
            stream   = self._pa.open(
                format            = FORMAT,
                channels          = CHANNELS,
                rate              = RATE,
                input             = True,
                frames_per_buffer = CHUNK
            )

            frames_per_chunk = int(RATE / CHUNK * CHUNK_SECS)
            print(f"  🎤 Recording... (chunks every {CHUNK_SECS}s)")

            while self._running:
                frames = []
                for _ in range(frames_per_chunk):
                    if not self._running:
                        break
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    frames.append(data)

                if frames and self._running:
                    wav_path = self._save_chunk(frames)
                    if wav_path:
                        self.callback(wav_path)

            stream.stop_stream()
            stream.close()

        except ImportError:
            print("  ⚠️  pyaudio not installed.")
            print("     Run: pip install pyaudio")
        except Exception as e:
            print(f"  ⚠️  Audio capture error: {e}")

    def _save_chunk(self, frames: list) -> str:
        """Save audio frames to a temp WAV file. Returns file path."""
        try:
            import pyaudio
            FORMAT = pyaudio.paInt16

            tmp = tempfile.NamedTemporaryFile(
                suffix  = ".wav",
                delete  = False,
                prefix  = "callaudit_chunk_"
            )
            wf = wave.open(tmp.name, "wb")
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self._pa.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b"".join(frames))
            wf.close()
            tmp.close()
            return tmp.name

        except Exception as e:
            print(f"  ⚠️  Chunk save error: {e}")
            return None

    @staticmethod
    def cleanup(wav_path: str):
        """Delete a temp WAV file after processing."""
        try:
            if wav_path and os.path.exists(wav_path):
                os.unlink(wav_path)
        except Exception:
            pass

if __name__ == "__main__":
    import time

    chunks = []

    def on_chunk(wav_path):
        chunks.append(wav_path)
        print(f"  ✅ Chunk received: {wav_path}")

    print("="*45)
    print("  Audio Capture Test — 10 seconds")
    print("="*45)
    print("  Speak into your microphone now!")

    capture = AudioCapture(on_chunk_callback=on_chunk)
    capture.start()
    time.sleep(10)
    capture.stop()

    print(f"\n  Total chunks : {len(chunks)}")
    print("✅ Audio capture test done")