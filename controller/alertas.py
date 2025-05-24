from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from schemas.alertas import AlertaCreateSchema
from service.alertas import (
    criar_alerta_db,
    listar_alertas_db,
    deletar_alerta_db
)
from dependencies.db import get_db

router = APIRouter()

@router.post("/{cnpj}", tags=["Alertas"])
def criar_alerta(cnpj: str, data: AlertaCreateSchema, db: Session = Depends(get_db)):
    alerta = criar_alerta_db(db, cnpj, data)
    if not alerta:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return alerta

@router.get("/{cnpj}", tags=["Alertas"])
def listar_alertas(cnpj: str, db: Session = Depends(get_db)):
    alertas = listar_alertas_db(db, cnpj)
    if alertas is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return alertas

@router.delete("/{alerta_id}", tags=["Alertas"])
def deletar_alerta(alerta_id: int, db: Session = Depends(get_db)):
    sucesso = deletar_alerta_db(db, alerta_id)
    if not sucesso:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    return {"message": "Alerta deletado com sucesso"}
