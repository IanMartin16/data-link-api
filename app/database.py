from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import get_settings


settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=settings.environment == "development"
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)

def seed_plan_limits():
    from app.models.plan_limits import PlanLimits, PLAN_LIMITS_SEED

    db = SessionLocal()

    try:
        for item in PLAN_LIMITS_SEED:
            existing = db.query(PlanLimits).filter(
                PlanLimits.plan == item["plan"]
            ).first()

            if existing:
                # Actualiza límites si cambiaste el seed
                for key, value in item.items():
                    setattr(existing, key, value)
            else:
                db.add(PlanLimits(**item))

        db.commit()
        print("✅ Plan limits seed completed")

    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding plan limits: {e}")
        raise

    finally:
        db.close()