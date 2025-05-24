from fastapi import APIRouter, Request, Query, Depends
from sqlalchemy.orm import Session

from schemas.user import UserSchema, OTPRequest
from schemas.userCredentials import UserCredentials
from service.user import (
    create_user_db, get_all_users_db, get_user_db, gerar_qrcode_otp_db,validar_otp_db,
    verify_login_db, logout_user_db,
     get_user_by_email_db
)
from dependencies.db import get_db
from dependencies.user import get_current_user_id

router = APIRouter()

#OTP
@router.get("/otp/qrcode")
def gerar_qrcode_otp(email: str = Query(...),db: Session = Depends(get_db)):
    return gerar_qrcode_otp_db(db, email)


@router.post("/otp")
def validar_otp(request: OTPRequest,db: Session = Depends(get_db)):
    return validar_otp_db(db, request)


@router.get("/all")
def listar_usuarios(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return get_all_users_db(db,user_id)

@router.get("", response_model=UserSchema)
def get_user(request: Request, db: Session = Depends(get_db)):
    return get_user_db(request, db)

@router.post("/logout")
def logout_user(request: Request, db: Session = Depends(get_db)):
    return logout_user_db(request, db)

@router.get("/email/{email}", response_model=UserSchema)
def buscar_user_por_email(email: str, db: Session = Depends(get_db)):
    return get_user_by_email_db(db, email)

@router.post("/login")
def login(user_credentials: UserCredentials, db: Session = Depends(get_db)):
    return verify_login_db(db, user_credentials)

@router.post("", response_model=UserSchema)
def create_user(user: UserSchema, db: Session = Depends(get_db)):
    return create_user_db(db, user)
