from datetime import datetime
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user import User


def reset_monthly_counters():
    """
    Reset monthly file counters.
    Intended to run on the 1st day of each month.
    """
    db: Session = SessionLocal()

    try:
        users = db.query(User).all()

        for user in users:
            user.files_processed_this_month = 0
            user.last_reset_date = datetime.utcnow()

        db.commit()
        print(f"✅ Reset {len(users)} user counters")

    except Exception as e:
        db.rollback()
        print(f"❌ Error resetting counters: {e}")
        raise

    finally:
        db.close()