# realtime/alert_engine.py
"""
Compliance Alert Engine.
Detects violations and sends:
  - In-app alerts (returned in API response)
  - Email alerts via Gmail SMTP
"""

import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "config" / ".env")

ALERT_EMAIL_FROM     = os.getenv("ALERT_EMAIL_FROM", "")
ALERT_EMAIL_PASSWORD = os.getenv("ALERT_EMAIL_PASSWORD", "")
ALERT_EMAIL_TO       = os.getenv("ALERT_EMAIL_TO", "")

SCORE_CRITICAL = 40
SCORE_WARNING  = 60


class AlertEngine:

    def __init__(self, socketio=None):
        self.socketio      = socketio
        self.alerts_sent   = []
        self.email_enabled = bool(
            ALERT_EMAIL_FROM and
            ALERT_EMAIL_PASSWORD and
            ALERT_EMAIL_TO
        )
        if self.email_enabled:
            print(f"  📧 Email alerts enabled → {ALERT_EMAIL_TO}")
        else:
            print(f"  📧 Email alerts disabled (add credentials to config/.env)")

    def check_and_alert(self, score_result: dict, transcript: str = "") -> list:
        """
        Check scored result for violations.
        Returns list of alert dicts.
        Sends email if credentials configured.
        """
        if not score_result:
            return []

        score      = score_result.get("overall_score", 0)
        grade      = score_result.get("grade", "?")
        violations = score_result.get("violations", [])
        alerts     = []

        # Score-based alerts
        if score < SCORE_CRITICAL:
            alerts.append({
                "level":   "CRITICAL",
                "message": f"Score critically low: {score}/100 (Grade {grade})",
                "score":   score,
                "time":    datetime.now().strftime("%H:%M:%S")
            })
        elif score < SCORE_WARNING:
            alerts.append({
                "level":   "WARNING",
                "message": f"Score below pass threshold: {score}/100 (Grade {grade})",
                "score":   score,
                "time":    datetime.now().strftime("%H:%M:%S")
            })

        # Violation-based alerts
        for v in violations:
            sev = (v.get("severity") or "").lower()
            if sev in ["critical", "high"]:
                alerts.append({
                    "level":   sev.upper(),
                    "message": (
                        f"[{sev.upper()}] "
                        f"{v.get('type','').replace('_',' ').title()} — "
                        f"{v.get('explanation','')[:100]}"
                    ),
                    "quote": v.get("quote", ""),
                    "time":  datetime.now().strftime("%H:%M:%S")
                })

        # Send alerts
        for alert in alerts:
            if self.socketio:
                self._send_inapp_alert(alert)
            if self.email_enabled:
                self._send_email_alert(alert, score_result)
            self.alerts_sent.append(alert)
            print(f"  🚨 ALERT [{alert['level']}]: {alert['message'][:80]}")

        return alerts

    def _send_inapp_alert(self, alert: dict):
        """Send via WebSocket if socketio available."""
        try:
            self.socketio.emit("compliance_alert", alert)
        except Exception as e:
            print(f"  ⚠️  WebSocket alert failed: {e}")

    def _send_email_alert(self, alert: dict, score_result: dict):
        """Send HTML email via Gmail SMTP."""
        try:
            msg            = MIMEMultipart("alternative")
            score          = score_result.get("overall_score", 0)
            grade          = score_result.get("grade", "?")
            msg["Subject"] = f"🚨 CallAudit Alert [{alert['level']}] — Score {score}/100"
            msg["From"]    = ALERT_EMAIL_FROM
            msg["To"]      = ALERT_EMAIL_TO

            violations = score_result.get("violations", [])
            viol_html  = "".join([
                f"<li><strong>[{v.get('severity','').upper()}]</strong> "
                f"{v.get('type','').replace('_',' ').title()} — "
                f"{v.get('explanation','')[:100]}</li>"
                for v in violations
            ])

            level_color = (
                "#f87171" if alert["level"] == "CRITICAL" else
                "#fb923c" if alert["level"] == "HIGH" else
                "#f59e0b"
            )

            html = f"""
            <html><body style="font-family:Arial;background:#f8f9fa;padding:20px">
            <div style="max-width:600px;margin:0 auto;background:white;
                        border-radius:12px;padding:24px;
                        border-left:6px solid {level_color}">

              <h2 style="margin-top:0;color:#111827">
                🚨 Compliance Alert — {alert['level']}
              </h2>

              <p style="font-size:15px;color:#374151">
                <strong>Time:</strong> {alert['time']}<br>
                <strong>Score:</strong> {score}/100 (Grade {grade})<br>
                <strong>Outcome:</strong> {score_result.get('call_outcome','Unknown')}
              </p>

              <div style="background:#fef2f2;border-radius:8px;
                          padding:16px;margin:16px 0;
                          border-left:4px solid {level_color}">
                <strong>Alert:</strong> {alert['message']}
              </div>

              {"<h3>Violations Detected:</h3><ul>" + viol_html + "</ul>" if violations else ""}

              <div style="background:#f1f5f9;border-radius:8px;
                          padding:12px;margin-top:16px">
                <strong>AI Summary:</strong><br>
                {score_result.get('summary','No summary available')}
              </div>

              <p style="color:#94a3b8;font-size:12px;margin-top:24px">
                CallAudit Pro — Automated Compliance Monitoring
              </p>
            </div>
            </body></html>
            """

            msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(ALERT_EMAIL_FROM, ALERT_EMAIL_PASSWORD)
                server.sendmail(ALERT_EMAIL_FROM, ALERT_EMAIL_TO, msg.as_string())

            print(f"  📧 Email alert sent to {ALERT_EMAIL_TO}")

        except Exception as e:
            print(f"  ⚠️  Email failed: {e}")