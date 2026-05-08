from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models.user import User

def reset_monthly_counters():
    """
    Reset monthly file counters (runs on 1st of each month)
    """
    db = SessionLocal()
    
    try:
        # Reset todos los usuarios
        users = db.query(User).all()
        
        for user in users:
            user.files_processed_this_month = 0
            user.last_reset_date = datetime.now()
        
        db.commit()
        
        print(f"✅ Reset {len(users)} user counters")
    
    except Exception as e:
        print(f"❌ Error resetting counters: {e}")
        db.rollback()
    
    finally:
        db.close()


# Schedule job
scheduler = BackgroundScheduler()
scheduler.add_job(
    reset_monthly_counters,
    'cron',
    day=1,  # 1st of month
    hour=0,
    minute=0
)
scheduler.start()