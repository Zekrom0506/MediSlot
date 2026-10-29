"""Load profile for the scale-out experiment (scripts/scale_test.sh).

Same patient behaviour as locustfile.py (search, view free times, book, cancel),
but without logging in: scripts/scale_test.sh creates a token for every seeded
patient beforehand (results/tokens.json). Logging in runs bcrypt, which is
deliberately slow, so with hundreds of users the first minutes of a run would
measure password hashing instead of the booking system. The normal load test
(locustfile.py) still includes logins.
"""

import itertools
import json
import threading
from pathlib import Path

from locustfile import Patient

TOKENS = json.loads((Path(__file__).parent / "results" / "tokens.json").read_text())
token_cycle = itertools.cycle(TOKENS)
token_lock = threading.Lock()


class ScalePatient(Patient):
    def on_start(self) -> None:
        with token_lock:
            token = next(token_cycle)
        self.client.headers["Authorization"] = f"Bearer {token}"
        self.doctor_ids: list[int] = []
        self.booking_ids: list[int] = []


# Only run ScalePatient, not the Patient class imported above.
Patient.abstract = True
