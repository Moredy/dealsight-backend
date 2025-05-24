from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from service.divida_ativa_uniao import (
    buscar_salvar_divida_ativa_uniao_db,
    consultar_divida_uniao_db
)

from service.divida_ativa_sp import (
    buscar_salvar_divida_ativa_sp_db,
    consultar_divida_sp_db
)

from dependencies.db import get_db

router = APIRouter()

# ----- União -----

@router.post("/uniao/buscar-salvar", tags=["Dívida Ativa - União"])
async def buscar_salvar_uniao(cnpj: str, db: Session = Depends(get_db)):
    return await buscar_salvar_divida_ativa_uniao_db(db, cnpj)

@router.get("/uniao/consulta", tags=["Dívida Ativa - União"])
def consultar_uniao(
    cnpj: str = Query(..., description="CNPJ da empresa"),
    db: Session = Depends(get_db)
):
    return consultar_divida_uniao_db(db, cnpj)

# ----- São Paulo -----

@router.post("/sp/buscar-salvar", tags=["Dívida Ativa - SP"])
async def buscar_salvar_sp(cnpj: str, db: Session = Depends(get_db)):
    return await buscar_salvar_divida_ativa_sp_db(db, cnpj)

@router.get("/sp/consulta", tags=["Dívida Ativa - SP"])
def consultar_sp(
    cnpj: str = Query(..., description="CNPJ da empresa"),
    db: Session = Depends(get_db)
):
    return consultar_divida_sp_db(db, cnpj)
