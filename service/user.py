import os

from schemas.user import UserSchema,OTPRequest
from schemas.userCredentials import UserCredentials
from model.models import User, Session
from datetime import datetime, timedelta
from fastapi import HTTPException, Request
from services.auth import generate_JWT_token
from jose import jwt, JWTError, ExpiredSignatureError
from services import auth
import pyotp
import qrcode
import io
import base64
from fastapi.responses import JSONResponse

SESSION_EXPIRATION_MINUTES = 60*8

def get_all_users_db(
    db,
    user_id,
):
    # Recupera o usuário atual
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Conta usuários na mesma organização
    count = db.query(User).filter(User.organizacao_id == user.organizacao_id).count()

    return {"usuarios": count}

def get_user_by_email_db(db, email):
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=400, detail= "Usuário não encontrado")
    
    return user

def get_user_db(request: Request, db):
    token = request.headers.get("authorization-otp")
    if not token:
        raise HTTPException(status_code=401, detail="Token ausente")

    try:
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=['HS256'])

        print(payload)
        user_id = payload.get("user_id")

        if not user_id:
            raise HTTPException(status_code=400, detail="Token não contém id")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        return user

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")


def logout_user_db(request: Request, db):
    token_web = request.headers.get("authorization-web")
    token_otp = request.headers.get("authorization-otp")

    if not token_web and not token_otp:
        raise HTTPException(status_code=401, detail="Tokens ausentes")

    # Remove sessões se os tokens existirem
    if token_web:
        session_web = db.query(Session).filter(Session.token == token_web).first()
        if session_web:
            db.delete(session_web)

    if token_otp:
        session_otp = db.query(Session).filter(Session.token == token_otp).first()
        if session_otp:
            db.delete(session_otp)

    db.commit()

    return {"detail": "Logout realizado com sucesso"}

def create_user_db(db, user:UserSchema):
    
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user is not None:
        raise HTTPException(status_code=400,detail="Usuário já cadastrado")

    new_user = User(
        firstName = user.firstName,
        lastName = user.lastName,
        email = user.email,
        cel = user.cel,
        password = user.password,
        gender = user.gender
    )

    db.add(new_user)
    db.commit()

    return new_user 

def verify_login_db(db, user: UserCredentials):

    email = user.email
    password = user.password

    # Verifica se o usuário existe no banco de dados
    db_user = db.query(User).filter(User.email == email).first()
    if db_user is None:
        raise HTTPException(status_code=400, detail="Email não existe")
    elif password != db_user.password:
        raise HTTPException(status_code=400, detail="Senha incorreta")

    return {"status" : "authorized"}


def gerar_qrcode_otp_db(db, email: str):
    # Verifica se o usuário existe
    db_user = db.query(User).filter(User.email == email).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Se o 2FA já estiver associado, retorna 204
    if db_user.two_factor_associated:
        return JSONResponse(status_code=204, content={"detail": "Two Factor já associado"})

    # Remove sessões antigas do tipo otp_seed
    db.query(Session).filter(
        Session.user_id == db_user.id,
        Session.type == "otp_seed"
    ).delete(synchronize_session=False)

    # Gera novo secret e cria nova sessão otp_seed
    otp_secret = pyotp.random_base32()
    otp_seed_session = Session(
        user_id=db_user.id,
        token=otp_secret,
        type="otp_seed",
        created_at=datetime.utcnow(),
        expires_at=None
    )
    db.add(otp_seed_session)
    db.commit()

    # Cria o QR code com o secret
    totp = pyotp.TOTP(otp_secret)
    uri = totp.provisioning_uri(name=email, issuer_name="Monitoramento")

    qr = qrcode.make(uri)
    buffered = io.BytesIO()
    qr.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode()

    return {"qrcode_base64": f"data:image/png;base64,{img_base64}"}



def is_valid_otp_token(token_otp: str, db) -> bool:
    otp_session = (
        db.query(Session)
        .filter(Session.token == token_otp, Session.type == "otp")
        .first()
    )

    return otp_session is not None and otp_session.expires_at >= datetime.utcnow()

def validar_otp_db(db: Session, request: OTPRequest):
    email = request.email
    codigo_otp = request.codigo_otp

    # Verifica se o usuário existe
    db_user = db.query(User).filter(User.email == email).first()
    if db_user is None:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    # Busca a última sessão do tipo 'otp_seed' (onde está o secret do OTP)
    otp_seed_session = (
        db.query(Session)
        .filter(Session.user_id == db_user.id, Session.type == "otp_seed")
        .order_by(Session.created_at.desc())
        .first()
    )

    if otp_seed_session is None or not otp_seed_session.token:
        raise HTTPException(status_code=400, detail="Chave OTP não encontrada para o usuário")

    otp_secret = otp_seed_session.token

    # Gera TOTP com base no secret da sessão
    totp = pyotp.TOTP(otp_secret)

    # Valida código OTP
    if not totp.verify(codigo_otp):
        raise HTTPException(status_code=401, detail="Código OTP inválido")

    # Gera token JWT
    jwt_token = generate_JWT_token(db_user.id, SESSION_EXPIRATION_MINUTES)

    # Cria nova sessão com o JWT
    new_session = Session(
        user_id=db_user.id,
        token=jwt_token,
        type="otp",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=SESSION_EXPIRATION_MINUTES)
    )

    # Atualiza two_factor_associated
    db_user.two_factor_associated = True

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    # Retorna dados
    return {
        "user_id": db_user.id,
        "email": db_user.email,
        "firstName": db_user.firstName,
        "lastName": db_user.lastName,
        "cel": db_user.cel,
        "gender": db_user.gender,
        "type": "otp",
        "token": jwt_token,
        "session_id": new_session.id,
        "expires_at": new_session.expires_at
    }
