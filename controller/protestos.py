from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from service.protestos import (
    consultar_gravar_protestos_por_cnpj_db,
    buscar_protesto_mais_recente_por_cnpj_db,
    calcular_risco_relevancia_medio_db
)
from dependencies.db import get_db

router = APIRouter()

@router.post("/{cnpj}", tags=["Protestos"])
async def consultar_e_gravar_protestos(cnpj: str, db: Session = Depends(get_db)):
    return await consultar_gravar_protestos_por_cnpj_db(cnpj, db)

@router.get("/buscar-mais-recente/{cnpj}", tags=["Protestos"])
def obter_protesto_mais_recente(cnpj: str, db: Session = Depends(get_db)):
    return buscar_protesto_mais_recente_por_cnpj_db(cnpj, db)

@router.get("/desempenho/{cnpj}", tags=["Protestos"])
def calcular_risco_relevancia_medio(cnpj: str, db: Session = Depends(get_db)):
    return calcular_risco_relevancia_medio_db(cnpj, db)
