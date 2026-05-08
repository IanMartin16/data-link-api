# Script para inicializar la base de datos con plan limits y usuario de prueba

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.user import User
from app.models.plan_limits import PlanLimits, PLAN_LIMITS_SEED
from app.database import Base
from app.config import get_settings

settings = get_settings()


def init_database():
    """
    Inicializa la base de datos:
    1. Crea todas las tablas
    2. Seed de plan_limits
    3. Usuario de prueba (opcional)
    """
    
    print("🚀 Inicializando base de datos...")
    
    # Crear engine
    engine = create_engine(settings.database_url)
    
    # Crear todas las tablas
    print("📊 Creando tablas...")
    Base.metadata.create_all(bind=engine)
    
    # Crear sesión
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        # Seed plan limits
        print("💰 Seeding plan limits...")
        
        for plan_data in PLAN_LIMITS_SEED:
            # Verificar si ya existe
            existing = db.query(PlanLimits).filter(
                PlanLimits.plan == plan_data["plan"]
            ).first()
            
            if not existing:
                plan_limit = PlanLimits(**plan_data)
                db.add(plan_limit)
                print(f"  ✅ Created {plan_data['plan']} plan limits")
            else:
                print(f"  ⏭️  {plan_data['plan']} already exists")
        
        db.commit()
        
        # Crear usuario de prueba (opcional)
        print("\n👤 Creating test user...")
        
        test_email = "test@datalink.com"
        existing_user = db.query(User).filter(User.email == test_email).first()
        
        if not existing_user:
            test_user = User(
                email=test_email,
                api_key=User.generate_api_key(),
                plan="FREE"
            )
            db.add(test_user)
            db.commit()
            
            print(f"  ✅ Created test user")
            print(f"     Email: {test_user.email}")
            print(f"     API Key: {test_user.api_key}")
            print(f"     Plan: {test_user.plan}")
        else:
            print(f"  ⏭️  Test user already exists")
            print(f"     API Key: {existing_user.api_key}")
        
        print("\n✅ Database initialization complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    
    finally:
        db.close()


if __name__ == "__main__":
    init_database()
