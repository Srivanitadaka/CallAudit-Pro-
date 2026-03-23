# realtime/alert_engine.py
"""
Compliance Alert Engine
─────────────────────────────────────────────
Detects violations in scored results and sends:
  - In-app alerts via Flask-SocketIO
  - Email alerts via Gmail SMTP

Add to config/.env:
  ALERT_EMAIL_FROM=your_gmail@gmail.com
  ALERT_EMAIL_PASSWORD=your_app_password
  ALERT_EMAIL_TO=supervisor@gmail.com
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
            print(f"  📧 Email alerts → {ALERT_EMAIL_TO}")
        else:
            print(f"  ⚠️  Email alerts disabled — add credentials to .env")

    # ══════════════════════════════════════════════════
    # MAIN CHECK
    # ══════════════════════════════════════════════════
    def check_and_alert(self, score_result: dict,
                        filename: str = "") -> list:
        """
        Check a scored result and fire alerts if needed.
        Call this after every analysis completes.
        Returns list of alerts fired.
        """
        if not score_result:
            return []

        score      = score_result.get("overall_score", 0)
        grade      = score_result.get("grade", "?")
        violations = score_result.get("violations", [])
        alerts     = []

        # ── Score-based alerts ─────────────────────────
        if score < SCORE_CRITICAL:
            alerts.append({
                "level":    "CRITICAL",
                "type":     "low_score",
                "message":  f"Score critically low: {score}/100 (Grade {grade})",
                "filename": filename,
                "score":    score,
                "time":     datetime.now().strftime("%H:%M:%S"),
            })

        elif score < SCORE_WARNING:
            alerts.append({
                "level":    "WARNING",
                "type":     "below_threshold",
                "message":  f"Score below pass threshold: {score}/100 (Grade {grade})",
                "filename": filename,
                "score":    score,
                "time":     datetime.now().strftime("%H:%M:%S"),
            })

        # ── Violation-based alerts ─────────────────────
        for v in violations:
            sev = (v.get("severity") or "medium").lower()
            if sev in ["critical", "high"]:
                alerts.append({
                    "level":    sev.upper(),
                    "type":     "violation",
                    "message":  (
                        f"[{sev.upper()}] "
                        f"{(v.get('type') or '').replace('_',' ').title()} — "
                        f"{(v.get('explanation') or '')[:100]}"
                    ),
                    "quote":    v.get("quote", ""),
                    "filename": filename,
                    "score":    score,
                    "time":     datetime.now().strftime("%H:%M:%S"),
                })

        # ── Send alerts ────────────────────────────────
        for alert in alerts:
            self._send_inapp(alert)
            if self.email_enabled:
                self._send_email(alert, score_result, filename)
            self.alerts_sent.append(alert)
            print(f"  🚨 [{alert['level']}] {alert['message'][:70]}")

        return alerts

    # ══════════════════════════════════════════════════
    # IN-APP ALERT
    # ══════════════════════════════════════════════════
    def _send_inapp(self, alert: dict):
        if self.socketio:
            self.socketio.emit("compliance_alert", alert)

    # ══════════════════════════════════════════════════
    # EMAIL ALERT
    # ══════════════════════════════════════════════════
    def _send_email(self, alert: dict,
                    score_result: dict, filename: str):
        try:
            score      = score_result.get("overall_score", 0)
            grade      = score_result.get("grade", "?")
            violations = score_result.get("violations", [])
            summary    = score_result.get("summary", "No summary")

            border_color = (
                "#f87171" if alert["level"] == "CRITICAL" else
                "#fb923c" if alert["level"] == "HIGH" else
                "#f59e0b"
            )

            viol_html = "".join([
                f"<li style='margin-bottom:8px'>"
                f"<strong style='color:{border_color}'>"
                f"[{(v.get('severity') or '').upper()}]</strong> "
                f"{(v.get('type') or '').replace('_',' ').title()} — "
                f"{(v.get('explanation') or '')[:100]}"
                f"{'<br><em style=color:#94a3b8>' + v.get('quote','') + '</em>' if v.get('quote') else ''}"
                f"</li>"
                for v in violations
            ])

            html = f"""
            <html><body style="font-family:Arial,sans-serif;
                               background:#f1f5f9;padding:24px">
            <div style="max-width:600px;margin:0 auto;
                        background:white;border-radius:12px;
                        padding:28px;
                        border-left:6px solid {border_color}">

              <h2 style="margin-top:0;color:#0f172a">
                🚨 Compliance Alert — {alert['level']}
              </h2>

              <table style="width:100%;border-collapse:collapse;
                            margin-bottom:20px">
                <tr>
                  <td style="padding:8px 0;color:#64748b;width:120px">
                    Time
                  </td>
                  <td style="padding:8px 0;font-weight:600">
                    {alert['time']}
                  </td>
                </tr>
                <tr>
                  <td style="padding:8px 0;color:#64748b">File</td>
                  <td style="padding:8px 0;font-weight:600">
                    {filename or 'Live call'}
                  </td>
                </tr>
                <tr>
                  <td style="padding:8px 0;color:#64748b">Score</td>
                  <td style="padding:8px 0;font-weight:600;
                             color:{border_color}">
                    {score}/100 — Grade {grade}
                  </td>
                </tr>
              </table>

              <div style="background:#fef2f2;border-radius:8px;
                          padding:16px;margin-bottom:20px;
                          border-left:4px solid {border_color}">
                <strong>Alert:</strong><br>
                {alert['message']}
              </div>

              {f'<h3 style="color:#0f172a">Violations ({len(violations)})</h3><ul style="padding-left:20px">{viol_html}</ul>' if violations else ''}

              <div style="background:#f8fafc;border-radius:8px;
                          padding:16px;margin-top:16px">
                <strong style="color:#64748b">AI Summary:</strong><br>
                <p style="margin:8px 0 0;color:#374151">{summary}</p>
              </div>

              <p style="color:#94a3b8;font-size:12px;
                        margin-top:24px;text-align:center">
                CallAudit Pro — Automated Compliance Monitoring<br>
                llama-3.3-70b · Groq · LangChain · RAG
              </p>
            </div>
            </body></html>
            """

            msg = MIMEMultipart("alternative")
            msg["Subject"] = (
                f"🚨 CallAudit [{alert['level']}] — "
                f"{filename or 'Live call'} — "
                f"Score {score}/100"
            )
            msg["From"] = ALERT_EMAIL_FROM
            msg["To"]   = ALERT_EMAIL_TO
            msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(ALERT_EMAIL_FROM, ALERT_EMAIL_PASSWORD)
                server.sendmail(
                    ALERT_EMAIL_FROM,
                    ALERT_EMAIL_TO,
                    msg.as_string()
                )
            print(f"  📧 Email sent → {ALERT_EMAIL_TO}")

        except Exception as e:
            print(f"  ⚠️  Email failed: {e}")


# ══════════════════════════════════════════════════════
# STANDALONE TEST
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\nTesting AlertEngine...\n")

    engine = AlertEngine(socketio=None)

    test_result = {
        "overall_score": 22,
        "grade":         "F",
        "call_outcome":  "Unresolved",
        "summary":       "Agent refused escalation and was dismissive.",
        "violations": [
            {
                "type":        "escalation_refused",
                "severity":    "critical",
                "quote":       "Managers are too busy",
                "explanation": "Agent refused customer request to speak to manager"
            },
            {
                "type":        "rude_language",
                "severity":    "high",
                "quote":       "There is nothing I can do",
                "explanation": "Dismissive language used"
            }
        ]
    }

    alerts = engine.check_and_alert(test_result, filename="test_call.mp3")
    print(f"\n{len(alerts)} alerts fired")
    for a in alerts:
        print(f"  [{a['level']}] {a['message']}")