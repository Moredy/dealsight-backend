from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import Optional

from service.juridico import (
    buscar_processos_jusfy_e_salvar_db,
    adicionar_fila_analise_db,
    consultar_processos_db,
    contar_processos_por_esfera_db,
    buscar_processos_transitados_em_julgado_db, consultar_indice_risco_db
)
from dependencies.db import get_db

router = APIRouter()

@router.post("/jusfy/processos/cadastro", tags=["Jurídico"])
async def processar_processos(
    cnpj: str,
    data_inicio: str,
    data_fim: str,
    db: Session = Depends(get_db)
):
    return await buscar_processos_jusfy_e_salvar_db(db, cnpj, data_inicio, data_fim)

@router.post("/jusfy/processos/adicionar-fila-analise", tags=["Jurídico"])
async def adicionar_fila(cnpj: str, db: Session = Depends(get_db)):
    return await adicionar_fila_analise_db(db, cnpj)

@router.get("/processos/consulta-db", tags=["Jurídico"])
async def consultar_processos(
    cnpj: str = Query(..., description="CNPJ da empresa"),
    data_inicio: date = Query(..., description="Data inicial no formato YYYY-MM-DD"),
    data_fim: date = Query(..., description="Data final no formato YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    return await consultar_processos_db(db, cnpj, data_inicio, data_fim)

@router.get("/processos/quantidade", tags=["Jurídico"])
async def quantidade_processos(
    cnpj: str = Query(..., description="CNPJ da empresa"),
    process_sphere: str = Query(..., description="Esfera processual (ex: cível, penal...)"),
    data_inicio: Optional[date] = Query(None, description="Data inicial no formato YYYY-MM-DD"),
    data_fim: Optional[date] = Query(None, description="Data final no formato YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    return await contar_processos_por_esfera_db(
        db=db,
        cnpj=cnpj,
        process_sphere=process_sphere,
        data_inicio=data_inicio,
        data_fim=data_fim
    )

@router.get("/processos/transitados-em-julgado", tags=["Jurídico"])
async def processos_transitados_em_julgado(
    cnpj: str = Query(..., description="CNPJ da empresa"),
    data_inicio: str = Query(..., description="Data de início no formato YYYY-MM-DD"),
    data_fim: str = Query(..., description="Data de fim no formato YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    data_inicio_date = datetime.strptime(data_inicio, "%Y-%m-%d").date()
    data_fim_date = datetime.strptime(data_fim, "%Y-%m-%d").date()
    return await buscar_processos_transitados_em_julgado_db(db, cnpj, data_inicio_date, data_fim_date)


@router.get("/desempenho/{cnpj}", tags=["Jurídico"])
async def indice_risco_endpoint(
    cnpj: str,
    data_inicio: str = Query(..., description="Data início (YYYY-MM-DD)"),
    data_fim: str = Query(..., description="Data fim (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    try:
        data_inicio_date = datetime.strptime(data_inicio, "%Y-%m-%d").date()
        data_fim_date = datetime.strptime(data_fim, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Datas devem estar no formato YYYY-MM-DD")

    return consultar_indice_risco_db(db, cnpj, data_inicio_date, data_fim_date)