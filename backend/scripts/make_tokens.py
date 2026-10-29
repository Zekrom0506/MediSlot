"""Print login tokens for every seeded patient, as a JSON list (for the scale load test).

Creating the tokens directly skips the password check, which runs bcrypt and is
deliberately slow. Otherwise the first minute of a load test would mostly measure
password hashing instead of searching and booking. Tokens last 30 minutes.

    docker compose run --rm migrate python -m scripts.make_tokens > load_tests/results/tokens.json
"""

import json

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.models import User
from app.models.enums import UserRole


def main() -> None:
    with SessionLocal() as db:
        patients = db.scalars(
            select(User).where(User.role == UserRole.PATIENT.value).where(User.email.like("patient%"))
        )
        tokens = [create_access_token(patient.id, patient.role) for patient in patients]
    print(json.dumps(tokens))


if __name__ == "__main__":
    main()
