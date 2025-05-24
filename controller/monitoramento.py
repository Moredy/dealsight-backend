from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from schemas.monitoramento import MonitoramentoBaseSchema
from dependencies.db import get_db
from service.monitoramento import (
    get_ultimo_status_modulo_db,
    get_monitoramento_db,
    update_monitoramento_db,
    get_desempenho_monitoramento,
    cron_cadastrar_dados_empresa_db,
    cron_cadastrar_processos_empresa_db,
    executar_cron_para_todas_empresas,
    executar_cron_para_todas_processos_empresas,
)

router = APIRouter()


# Responsável pelo gerenciamento dos módulos


# Consultas gerais
@router.get("/status/{cnpj}", tags=["Monitoramento"])
def status_modulo(cnpj: str, modulo: str, db: Session = Depends(get_db)):
    return get_ultimo_status_modulo_db(cnpj, modulo, db)

@router.get("/{cnpj}", tags=["Monitoramento"])
def consultar_monitoramento(cnpj: str, modulo: str, db: Session = Depends(get_db)):
    return get_monitoramento_db(cnpj, modulo, db)

@router.patch("/{cnpj}", tags=["Monitoramento"])
def atualizar_monitoramento(cnpj: str, update_data: MonitoramentoBaseSchema, db: Session = Depends(get_db)):
    return update_monitoramento_db(cnpj, update_data, db)

@router.get("/desempenho/{cnpj}", tags=["Monitoramento"])
def desempenho_monitoramento(cnpj: str, db: Session = Depends(get_db)):
    return get_desempenho_monitoramento(cnpj, db)

# Execução manual dos crons
@router.post("/cron/scrapping-empresa/{cnpj}", tags=["Monitoramento - Cron"])
async def cron_dados_empresa(cnpj: str):
    return await cron_cadastrar_dados_empresa_db(cnpj)

@router.post("/cron/scrapping-processos/{cnpj}", tags=["Monitoramento - Cron"])
async def cron_processos_empresa(cnpj: str):
    return await cron_cadastrar_processos_empresa_db(cnpj)

@router.post("/cron/cadastrar-dados-modulos", tags=["Monitoramento - Cron"])
async def cron_dados_todas_empresas(db: Session = Depends(get_db)):
    return await executar_cron_para_todas_empresas(db)

@router.post("/cron/cadastrar-dados-juridico", tags=["Monitoramento - Cron"])
async def cron_processos_todas_empresas(db: Session = Depends(get_db)):
    return await executar_cron_para_todas_processos_empresas(db)
