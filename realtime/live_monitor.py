# realtime/live_monitor.py
"""
LiveMonitor — orchestrates microphone capture + transcription + scoring.

stop() is designed to NEVER raise into the Streamlit main thread.
All PyAudio work happens inside AudioCapture which runs teardown
off the main thread (see audio_capture.py).
"""

import sys
import threading
import time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from realtime.audio_capture     import AudioCapture
from realtime.stream_transcriber import StreamTranscriber
from realtime.alert_engine       import AlertEngine

SCORE_INTERVAL_SECS = 15


class LiveMonitor:

    def __init__(self, socketio=None):
        self.socketio      = socketio
        self.is_running    = False
        self.start_time    = None
        self.current_score = None
        self.all_alerts    = []
        self.transcript    = ""

        self.alert_engine = AlertEngine(socketio=socketio)

        self.transcriber = StreamTranscriber(
            on_transcript_callback=self._on_new_transcript)

        self.audio_capture = AudioCapture(
            on_chunk_callback=self._on_audio_chunk)

        try:
            from rag_pipeline.rag_pipeline import RAGPipeline
            self.pipeline = RAGPipeline(backend="chromadb")
            self.pipeline.setup()
        except BaseException as e:
            print(f"  RAG Pipeline setup failed: {e}")
            self.pipeline = None

        self._score_timer = None

    # ── Start ─────────────────────────────────────────────

    def start(self) -> dict:
        if self.is_running:
            return {"status": "already_running"}

        self.is_running = True
        self.start_time = datetime.now()
        self.transcript = ""
        self.all_alerts = []
        self.transcriber.reset()

        self.audio_capture.start()
        self._schedule_scoring()

        print(f"  LIVE MONITORING STARTED  {self.start_time.strftime('%H:%M:%S')}")

        if self.socketio:
            try:
                self.socketio.emit("monitor_started",
                    {"time": self.start_time.strftime("%H:%M:%S")})
            except BaseException:
                pass

        return {"status": "started"}

    # ── Stop ──────────────────────────────────────────────

    def stop(self) -> dict:
        """
        Safely stop monitoring.
        Never raises — all errors are caught internally.
        Returns a dict with 'transcript' always present.
        """
        self.is_running = False

        # Cancel score timer
        try:
            if self._score_timer is not None:
                self._score_timer.cancel()
                self._score_timer = None
        except BaseException:
            pass

        # Stop audio (runs PyAudio teardown in background thread internally)
        try:
            self.audio_capture.stop()
        except BaseException as e:
            print(f"  Audio stop error (ignored): {e}")

        # Collect transcript
        try:
            live = self.transcriber.get_transcript()
            if live and live.strip():
                self.transcript = live
        except BaseException:
            pass

        duration = 0
        try:
            if self.start_time:
                duration = (datetime.now() - self.start_time).seconds
        except BaseException:
            pass

        print(f"  MONITORING STOPPED  duration={duration}s  "
              f"transcript={len(self.transcript)} chars")

        return {
            "status":     "stopped",
            "duration":   duration,
            "transcript": self.transcript,
            "alerts":     self.all_alerts,
        }

    # ── Status ────────────────────────────────────────────

    def get_status(self) -> dict:
        duration = 0
        try:
            if self.start_time:
                duration = (datetime.now() - self.start_time).seconds
        except BaseException:
            pass

        try:
            live = self.transcriber.get_transcript()
            if live and live.strip():
                self.transcript = live
        except BaseException:
            pass

        return {
            "is_running":    self.is_running,
            "duration":      duration,
            "transcript":    self.transcript,
            "current_score": self.current_score,
            "alerts":        self.all_alerts[-10:],
        }

    # ── Internal callbacks ────────────────────────────────

    def _on_audio_chunk(self, wav_path: str):
        if not self.is_running:
            try:
                AudioCapture.cleanup(wav_path)
            except BaseException:
                pass
            return

        t = threading.Thread(
            target=self._transcribe_chunk,
            args=(wav_path,), daemon=True)
        t.start()

    def _transcribe_chunk(self, wav_path: str):
        try:
            self.transcriber.transcribe_chunk(wav_path)
        except BaseException as e:
            print(f"  Transcribe error: {e}")
        finally:
            try:
                AudioCapture.cleanup(wav_path)
            except BaseException:
                pass

    def _on_new_transcript(self, new_text: str, full: str):
        self.transcript = full
        if self.socketio:
            try:
                self.socketio.emit("transcript_update",
                    {"new_text": new_text, "full_text": full[-3000:]})
            except BaseException:
                pass

    # ── Periodic scoring ──────────────────────────────────

    def _schedule_scoring(self):
        if not self.is_running:
            return
        self._score_timer = threading.Timer(
            SCORE_INTERVAL_SECS, self._scoring_tick)
        self._score_timer.daemon = True
        self._score_timer.start()

    def _scoring_tick(self):
        if not self.is_running:
            return
        self._run_score()
        self._schedule_scoring()

    def _run_score(self) -> dict:
        try:
            live = self.transcriber.get_transcript()
            if live and live.strip():
                self.transcript = live
        except BaseException:
            pass

        if not self.transcript.strip():
            return None
        if not self.pipeline:
            return None

        try:
            from llm.langchain_scorer import score_with_langchain
            enriched = self.pipeline.enrich(self.transcript)
            result   = score_with_langchain(enriched)
            if result:
                self.current_score = result
                try:
                    alerts = self.alert_engine.check_and_alert(
                        result, self.transcript)
                    if alerts:
                        self.all_alerts.extend(alerts)
                except BaseException:
                    pass
                if self.socketio:
                    try:
                        self.socketio.emit("score_update", {
                            "score":      result.get("overall_score", 0),
                            "grade":      result.get("grade", "?"),
                            "violations": result.get("violations", []),
                            "summary":    result.get("summary", ""),
                            "dimensions": result.get("dimension_scores", {}),
                        })
                    except BaseException:
                        pass
            return result
        except BaseException as e:
            print(f"  Live scoring error: {e}")
            return None