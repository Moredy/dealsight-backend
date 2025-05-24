from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from service.avisos import (
    listar_avisos_por_cnpj_db,
    listar_todos_avisos_db
)
from dependencies.db import get_db
from dependencies.user import get_current_user_id

router = APIRouter()

@router.get("/{cnpj}", tags=["Avisos"])
async def get_avisos_por_cnpj(cnpj: str, db: Session = Depends(get_db)):
    return await listar_avisos_por_cnpj_db(db, cnpj)

@router.get("", tags=["Avisos"])
async def get_todos_avisos(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    try:
        return await listar_todos_avisos_db(db, user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar avisos: {str(e)}")
