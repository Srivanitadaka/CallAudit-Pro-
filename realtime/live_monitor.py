# realtime/live_monitor.py
"""
Live Call Monitor
─────────────────────────────────────────────
Orchestrates real-time call monitoring.
Coordinates audio capture, transcription,
RAG scoring, and compliance alerts.

Usage:
  from realtime.live_monitor import LiveMonitor
  monitor = LiveMonitor(socketio=socketio)
  monitor.start()
  monitor.stop()
"""

import sys
import threading
import time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from realtime.audio_capture      import AudioCapture
from realtime.stream_transcriber  import StreamTranscriber
from realtime.alert_engine        import AlertEngine

SCORE_INTERVAL_SECS = 30   # score every 30 seconds


class LiveMonitor:

    def __init__(self, socketio=None):
        """
        socketio: Flask-SocketIO instance for real-time updates.
                  Can be None for testing without WebSocket.
        """
        self.socketio      = socketio
        self.is_running    = False
        self.start_time    = None
        self.current_score = None
        self.all_alerts    = []
        self.transcript    = ""

        # ── Components ─────────────────────────────────
        self.alert_engine = AlertEngine(socketio=socketio)

        self.transcriber  = StreamTranscriber(
            on_transcript_callback = self._on_new_transcript
        )
        self.audio_capture = AudioCapture(
            on_chunk_callback = self._on_audio_chunk
        )

        # ── RAG Pipeline ────────────────────────────────
        try:
            from rag_pipeline.rag_pipeline import RAGPipeline
            self.pipeline = RAGPipeline(backend="chromadb")
            self.pipeline.setup()
        except Exception as e:
            print(f"  ⚠️  RAG Pipeline setup failed: {e}")
            self.pipeline = None

        # ── Score timer ─────────────────────────────────
        self._score_timer = None

    # ══════════════════════════════════════════════════
    # START
    # ══════════════════════════════════════════════════
    def start(self) -> dict:
        """Start live call monitoring."""
        if self.is_running:
            return {"status": "already_running"}

        self.is_running  = True
        self.start_time  = datetime.now()
        self.transcript  = ""
        self.all_alerts  = []
        self.transcriber.reset()

        # Start audio capture
        self.audio_capture.start()

        # Start periodic scoring
        self._schedule_scoring()

        print(f"\n  🔴 LIVE MONITORING STARTED")
        print(f"     Time: {self.start_time.strftime('%H:%M:%S')}")

        if self.socketio:
            self.socketio.emit("monitor_started", {
                "time": self.start_time.strftime("%H:%M:%S")
            })

        return {"status": "started"}

    # ══════════════════════════════════════════════════
    # STOP
    # ══════════════════════════════════════════════════
    def stop(self) -> dict:
        """Stop live call monitoring and return final result."""
        if not self.is_running:
            return {"status": "not_running"}

        self.is_running = False
        self.audio_capture.stop()

        if self._score_timer:
            self._score_timer.cancel()

        # Run final score
        final    = self._run_score()
        duration = (datetime.now() - self.start_time).seconds

        print(f"\n  ⏹  MONITORING STOPPED")
        print(f"     Duration : {duration}s")
        if final:
            print(f"     Final    : Grade {final.get('grade')} | "
                  f"{final.get('overall_score')}/100")

        if self.socketio:
            self.socketio.emit("monitor_stopped", {
                "duration":    duration,
                "final_score": final
            })

        return {
            "status":      "stopped",
            "duration":    duration,
            "final_score": final,
            "alerts":      self.all_alerts,
            "transcript":  self.transcript
        }

    # ══════════════════════════════════════════════════
    # GET STATUS
    # ══════════════════════════════════════════════════
    def get_status(self) -> dict:
        """Return current monitoring status."""
        duration = 0
        if self.start_time:
            duration = (datetime.now() - self.start_time).seconds

        return {
            "is_running":    self.is_running,
            "duration":      duration,
            "transcript":    self.transcript[-2000:],
            "current_score": self.current_score,
            "alerts":        self.all_alerts[-10:],
        }

    # ══════════════════════════════════════════════════
    # INTERNAL CALLBACKS
    # ══════════════════════════════════════════════════
    def _on_audio_chunk(self, wav_path: str):
        """Called every 5 seconds with new audio chunk."""
        if not self.is_running:
            AudioCapture.cleanup(wav_path)
            return

        # Transcribe in separate thread so audio capture is not blocked
        thread = threading.Thread(
            target = self._transcribe_and_cleanup,
            args   = (wav_path,),
            daemon = True
        )
        thread.start()

    def _transcribe_and_cleanup(self, wav_path: str):
        """Transcribe chunk then delete temp file."""
        try:
            self.transcriber.transcribe_chunk(wav_path)
        finally:
            AudioCapture.cleanup(wav_path)

    def _on_new_transcript(self, new_text: str, full_transcript: str):
        """Called every time new transcript text arrives."""
        self.transcript = full_transcript

        if self.socketio:
            self.socketio.emit("transcript_update", {
                "new_text":  new_text,
                "full_text": full_transcript[-3000:]
            })

    # ══════════════════════════════════════════════════
    # PERIODIC SCORING
    # ══════════════════════════════════════════════════
    def _schedule_scoring(self):
        """Schedule next scoring cycle."""
        if not self.is_running:
            return
        self._score_timer = threading.Timer(
            SCORE_INTERVAL_SECS,
            self._scoring_tick
        )
        self._score_timer.daemon = True
        self._score_timer.start()

    def _scoring_tick(self):
        """Run score then schedule next cycle."""
        if not self.is_running:
            return
        self._run_score()
        self._schedule_scoring()

    def _run_score(self) -> dict:
        """Score current transcript using RAG + LangChain."""
        if not self.transcript.strip():
            return None

        if not self.pipeline:
            print("  ⚠️  RAG Pipeline not available")
            return None

        try:
            from llm.langchain_scorer import score_with_langchain

            print(f"\n  ⚡ Running live score...")
            enriched = self.pipeline.enrich(self.transcript)
            result   = score_with_langchain(enriched)

            if result:
                self.current_score = result

                # Check compliance alerts
                alerts = self.alert_engine.check_and_alert(
                    result, self.transcript
                )
                if alerts:
                    self.all_alerts.extend(alerts)

                # Push score update to dashboard
                if self.socketio:
                    self.socketio.emit("score_update", {
                        "score":      result.get("overall_score", 0),
                        "grade":      result.get("grade", "?"),
                        "violations": result.get("violations", []),
                        "summary":    result.get("summary", ""),
                        "dimensions": result.get("dimension_scores", {})
                    })

            return result

        except Exception as e:
            print(f"  ⚠️  Live scoring failed: {e}")
            return None





# ══════════════════════════════════════════════════════
# RUN DIRECTLY — test
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    import time

    print("="*50)
    print("  Live Monitor Test — 20 seconds")
    print("="*50)
    print("  Speak into your microphone!")
    print("  Transcript updates every 5 seconds")
    print("  Score appears after 30 seconds")
    print("="*50)

    monitor = LiveMonitor(socketio=None)
    result  = monitor.start()
    print(f"\n  Status: {result['status']}")

    for i in range(20, 0, -1):
        print(f"  Monitoring... {i}s remaining", end="\r")
        time.sleep(1)

    print("\n  Stopping...")
    final = monitor.stop()

    print(f"\n{'='*50}")
    print(f"  RESULTS")
    print(f"{'='*50}")
    print(f"  Duration   : {final['duration']}s")
    print(f"  Transcript : {final['transcript'][:300]}")
    print(f"  Alerts     : {len(final['alerts'])}")

    if final.get("final_score"):
        s = final["final_score"]
        print(f"  Grade      : {s.get('grade')}")
        print(f"  Score      : {s.get('overall_score')}/100")

    print("✅ Live monitor test done")