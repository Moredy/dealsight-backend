from fastapi import Request, HTTPException

def get_current_user_id(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Usuário não autenticado")
    return user_id