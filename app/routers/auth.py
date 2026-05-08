# app/routers/auth.py
"""
Router de autenticación - Signup de usuarios

USAR DESPUÉS: Cuando tengas frontend y quieras auto-registro
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.models.user import User
from app.models.plan_limits import PlanLimits


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr


class SignupResponse(BaseModel):
    email: str
    api_key: str
    plan: str
    message: str


@router.post("/signup", response_model=SignupResponse)
async def signup(
    request: SignupRequest,
    db: Session = Depends(get_db)
):
    """
    Registra un nuevo usuario con plan FREE
    
    Body:
        {
            "email": "user@example.com"
        }
    
    Returns:
        {
            "email": "user@example.com",
            "api_key": "abc123...",
            "plan": "FREE",
            "message": "Account created successfully"
        }
    """
    
    # 1. Verificar si el email ya existe
    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )
    
    # 2. Crear usuario FREE
    user = User(
        email=request.email,
        api_key=User.generate_api_key(),
        plan="FREE"
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # 3. Obtener límites del plan FREE
    limits = db.query(PlanLimits).filter(PlanLimits.plan == "FREE").first()
    
    return SignupResponse(
        email=user.email,
        api_key=user.api_key,
        plan=user.plan,
        message=f"Account created! You have {limits.files_per_month} files/month on the FREE plan."
    )


# OPCIONAL: Endpoint para validar si un email ya está registrado
@router.get("/check-email/{email}")
async def check_email(email: str, db: Session = Depends(get_db)):
    """
    Verifica si un email ya está registrado
    
    Útil para el frontend antes de intentar signup
    """
    
    existing = db.query(User).filter(User.email == email).first()
    
    return {
        "email": email,
        "available": existing is None
    }