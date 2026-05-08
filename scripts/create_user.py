#!/usr/bin/env python3
"""
Script para crear usuarios FREE con API key

Uso:
    python scripts/create_user.py email@example.com
    python scripts/create_user.py email@example.com STARTER
"""

import sys
import os

# Agregar ruta del proyecto al PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import User
from app.models.plan_limits import PlanLimits


def create_user(email: str, plan: str = "FREE"):
    """
    Crea un nuevo usuario con API key
    
    Args:
        email: Email del usuario
        plan: FREE, STARTER, PRO, o BUSINESS (default: FREE)
    
    Returns:
        User object o None si falla
    """
    
    db = SessionLocal()
    
    try:
        # Validar que el plan existe
        plan_limits = db.query(PlanLimits).filter(PlanLimits.plan == plan).first()
        if not plan_limits:
            print(f"❌ Error: Plan '{plan}' no existe")
            print(f"   Planes válidos: FREE, STARTER, PRO, BUSINESS")
            return None
        
        # Verificar si el usuario ya existe
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"❌ Error: Usuario {email} ya existe")
            print(f"   API Key existente: {existing.api_key}")
            print(f"   Plan actual: {existing.plan}")
            return None
        
        # Crear usuario
        user = User(
            email=email,
            api_key=User.generate_api_key(),
            plan=plan
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        print("=" * 60)
        print("✅ Usuario creado exitosamente!")
        print("=" * 60)
        print(f"📧 Email:    {user.email}")
        print(f"🔑 API Key:  {user.api_key}")
        print(f"💰 Plan:     {user.plan}")
        print(f"📊 Límites:")
        print(f"   • {plan_limits.files_per_month} archivos/mes")
        print(f"   • {plan_limits.max_file_size_mb} MB por archivo")
        print(f"   • {plan_limits.requests_per_hour} requests/hora")
        print("=" * 60)
        print("\n🧪 Probar:")
        print(f'   curl -H "X-API-Key: {user.api_key}" \\')
        print(f'        http://localhost:8000/api/v1/usage')
        print()
        
        return user
        
    except Exception as e:
        print(f"❌ Error al crear usuario: {e}")
        db.rollback()
        return None
        
    finally:
        db.close()


def list_users():
    """Lista todos los usuarios"""
    
    db = SessionLocal()
    
    try:
        users = db.query(User).order_by(User.created_at.desc()).all()
        
        if not users:
            print("📭 No hay usuarios registrados")
            return
        
        print("\n" + "=" * 80)
        print(f"{'Email':<30} {'Plan':<10} {'Files/Month':<12} {'Created':<20}")
        print("=" * 80)
        
        for user in users:
            files = f"{user.files_processed_this_month}/∞" if user.plan == "BUSINESS" else f"{user.files_processed_this_month}/10" if user.plan == "FREE" else f"{user.files_processed_this_month}/100" if user.plan == "STARTER" else f"{user.files_processed_this_month}/500"
            created = user.created_at.strftime("%Y-%m-%d %H:%M")
            print(f"{user.email:<30} {user.plan:<10} {files:<12} {created:<20}")
        
        print("=" * 80)
        print(f"Total: {len(users)} usuarios\n")
        
    finally:
        db.close()


if __name__ == "__main__":
    
    # Si piden listar
    if len(sys.argv) == 2 and sys.argv[1] == "--list":
        list_users()
        sys.exit(0)
    
    # Validar argumentos
    if len(sys.argv) < 2:
        print("❌ Uso:")
        print("   python scripts/create_user.py email@example.com")
        print("   python scripts/create_user.py email@example.com STARTER")
        print("   python scripts/create_user.py --list")
        print()
        print("Planes disponibles: FREE, STARTER, PRO, BUSINESS")
        sys.exit(1)
    
    email = sys.argv[1]
    plan = sys.argv[2] if len(sys.argv) > 2 else "FREE"
    
    # Crear usuario
    user = create_user(email, plan.upper())
    
    if user:
        sys.exit(0)
    else:
        sys.exit(1)