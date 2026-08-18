"""Create the first administrator account (production-safe).

Usage:
    python create_admin.py admin@yourcity.gov.et "Full Name"

The password is read interactively (or from CL_ADMIN_PASSWORD env var for
non-interactive provisioning). Never passes secrets on the command line.
"""
import getpass
import os
import sys

from app.db import Base, SessionLocal, engine
from app.models import Role, User
from app.security import hash_password


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    email = sys.argv[1].lower()
    name = sys.argv[2] if len(sys.argv) > 2 else "Administrator"
    password = os.environ.get("CL_ADMIN_PASSWORD") or getpass.getpass("Admin password (min 8 chars): ")
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        raise SystemExit(1)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            existing.role = Role.admin
            existing.is_active = True
            db.commit()
            print(f"Existing user {email} promoted to admin.")
            return
        db.add(User(name=name, email=email, role=Role.admin,
                    password_hash=hash_password(password)))
        db.commit()
        print(f"Admin account created: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
