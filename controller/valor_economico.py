from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from service.valor_economico import (
    buscar_salvar_dados_valor_economico_db,
    consultar_noticias_valor_economico_cnpj_db,
consultar_risco_valor_economico_db
)
from dependencies.db import get_db

router = APIRouter()

@router.post("/buscar-salvar", tags=["Valor Econômico"])
async def buscar_salvar_valor_economico(db: Session = Depends(get_db)):
    return await buscar_salvar_dados_valor_economico_db(db)

@router.get("/movimentacoes-falimentares", tags=["Valor Econômico"])
async def consultar_movimentacoes(
    cnpj: str = Query(..., description="CNPJ da empresa"),
    db: Session = Depends(get_db)
):
    return await consultar_noticias_valor_economico_cnpj_db(db, cnpj)


@router.get("/desempenho", tags=["Valor Econômico"])
async def consultar_movimentacoes(
    cnpj: str = Query(..., description="CNPJ da empresa"),
    db: Session = Depends(get_db)
):
    return await consultar_risco_valor_economico_db(db, cnpj)