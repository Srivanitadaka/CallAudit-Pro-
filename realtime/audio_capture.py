# realtime/audio_capture.py
"""
AudioCapture — records microphone in 5-second WAV chunks.

Key design decisions that prevent Streamlit crashes:
  1. stop() runs ALL PyAudio cleanup in a BACKGROUND THREAD — the Streamlit
     main thread never touches PyAudio directly, so SystemExit / OSError
     from PyAudio cannot reach Streamlit's script runner.
  2. Every PyAudio call is wrapped in `except BaseException` (not just
     `except Exception`) because PyAudio on Windows raises SystemExit,
     which is a BaseException subclass and bypasses bare except blocks.
  3. The capture loop and the WAV-writer are in separate daemon threads
     connected by a queue — neither can block or crash the other.
"""

import os
import wave
import queue
import threading
import tempfile

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False

CHUNK_SECONDS  = 5
SAMPLE_RATE    = 16000
CHANNELS       = 1
FORMAT_WIDTH   = 2
FRAMES_PER_BUF = 1024


class AudioCapture:

    def __init__(self, on_chunk_callback=None):
        self.callback       = on_chunk_callback
        self._running       = False
        self._pa            = None
        self._stream        = None
        self._chunk_q       = queue.Queue()
        self._cap_thread    = None
        self._writer_thread = None

    # ── Public API ────────────────────────────────────────

    def start(self):
        if self._running:
            return
        if not PYAUDIO_AVAILABLE:
            print("  pyaudio not installed. Run: pip install pyaudio")
            return

        self._running = True
        self._drain_queue()

        self._writer_thread = threading.Thread(
            target=self._writer_loop, daemon=True, name="wav-writer")
        self._writer_thread.start()

        self._cap_thread = threading.Thread(
            target=self._capture_loop, daemon=True, name="mic-capture")
        self._cap_thread.start()

        print("  Microphone capture started")

    def stop(self):
        """
        Signal stop and run ALL PyAudio cleanup in a background thread.
        Returns immediately so the Streamlit main thread is never blocked
        and SystemExit from PyAudio.terminate() can never reach Streamlit.
        """
        self._running = False
        self._chunk_q.put(None)   # wake writer so it exits cleanly

        t = threading.Thread(
            target=self._cleanup_pyaudio, daemon=True, name="pa-cleanup")
        t.start()
        t.join(timeout=5)         # wait at most 5 seconds, then move on

        print("  Audio capture stopped")

    @staticmethod
    def cleanup(wav_path: str):
        try:
            if wav_path and os.path.exists(wav_path):
                os.remove(wav_path)
        except BaseException:
            pass

    # ── PyAudio teardown (always off the main thread) ─────

    def _cleanup_pyaudio(self):
        try:
            s = self._stream
            if s is not None:
                self._stream = None
                try:
                    s.stop_stream()
                except BaseException:
                    pass
                try:
                    s.close()
                except BaseException:
                    pass
        except BaseException:
            pass

        try:
            pa = self._pa
            if pa is not None:
                self._pa = None
                try:
                    pa.terminate()
                except BaseException:
                    pass
        except BaseException:
            pass

    # ── Capture loop (daemon thread) ──────────────────────

    def _capture_loop(self):
        try:
            self._pa     = pyaudio.PyAudio()
            self._stream = self._pa.open(
                format            = pyaudio.paInt16,
                channels          = CHANNELS,
                rate              = SAMPLE_RATE,
                input             = True,
                frames_per_buffer = FRAMES_PER_BUF,
            )

            frames_needed = int(SAMPLE_RATE / FRAMES_PER_BUF * CHUNK_SECONDS)
            buf = []

            print(f"  Recording in {CHUNK_SECONDS}s chunks...")

            while self._running:
                try:
                    data = self._stream.read(
                        FRAMES_PER_BUF, exception_on_overflow=False)
                    buf.append(data)
                except OSError:
                    continue
                except BaseException:
                    break

                if len(buf) >= frames_needed:
                    self._chunk_q.put(list(buf))
                    buf = []

            if buf:
                self._chunk_q.put(list(buf))

        except BaseException as e:
            print(f"  Capture loop error: {e}")
        finally:
            self._running = False
            # cleanup thread handles PyAudio teardown

    # ── WAV writer loop (daemon thread) ───────────────────

    def _writer_loop(self):
        while True:
            try:
                item = self._chunk_q.get(timeout=1)
            except queue.Empty:
                if not self._running:
                    break
                continue

            if item is None:
                break

            path = self._write_wav(item)
            if path and self.callback:
                try:
                    self.callback(path)
                except BaseException as e:
                    print(f"  Chunk callback error: {e}")
                    self.cleanup(path)

    def _write_wav(self, frames: list) -> str:
        try:
            tmp  = tempfile.NamedTemporaryFile(
                suffix=".wav", delete=False, dir=tempfile.gettempdir())
            path = tmp.name
            tmp.close()
            with wave.open(path, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(FORMAT_WIDTH)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(b"".join(frames))
            return path
        except BaseException as e:
            print(f"  WAV write error: {e}")
            return ""

    def _drain_queue(self):
        while True:
            try:
                self._chunk_q.get_nowait()
            except queue.Empty:
                break