from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from datetime import datetime
from database import SessionLocal
from model.models import Session
import re

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Libera requisições OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Rotas públicas (regex safe)
        rotas_publicas = [r"^/user/login$", r"^/user/otp/qrcode$", r"^/user/otp$", r".*sintese.*"]
        for rota in rotas_publicas:
            if re.match(rota, request.url.path):
                return await call_next(request)

        token_jwt = request.headers.get("authorization-otp")
        if not token_jwt:
            return JSONResponse({"detail": "Sessão não encontrada"}, status_code=401)

        db = None
        try:
            db = SessionLocal()

            session_web = db.query(Session).filter(Session.token == token_jwt).first()
            if not session_web:
                return JSONResponse({"detail": "Sessão inválida"}, status_code=401)

            if session_web.expires_at and session_web.expires_at < datetime.utcnow():
                db.delete(session_web)
                db.commit()
                return JSONResponse({"detail": "Sessão expirada"}, status_code=401)

            request.state.user_id = session_web.user_id
            return await call_next(request)

        finally:
            if db:
                db.close()