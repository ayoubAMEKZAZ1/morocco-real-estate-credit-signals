"""Log of pipeline steps (feeds the diagnostics file)."""
import logging
import time

from .state import now_iso

log = logging.getLogger("ipai")


class RunLog:
    def __init__(self, run_id):
        self.run_id = run_id
        self.steps = []      # processing steps
        self.anomalies = []  # anomalies and missing values

    def step(self, stage, action, status="OK", detail=""):
        self.steps.append({"timestamp": now_iso(), "stage": stage, "action": action,
                           "status": status, "detail": detail})
        log.info("[%s] %s — %s %s", stage, action, status, detail)

    def anomaly(self, severity, category, subject, message):
        self.anomalies.append({"severity": severity, "category": category,
                               "subject": subject, "message": message})
        log.warning("ANOMALY %s %s %s: %s", severity, category, subject, message)

    def has_errors(self):
        return any(a["severity"] == "ERROR" for a in self.anomalies)
