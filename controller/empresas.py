from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Body, Query
from sqlalchemy.orm import Session
from typing import Optional

from schemas.empresas import EmpresaSchema
from service.empresas import (
    create_empresa_db,
    get_all_empresas_db,
    delete_empresa_by_cnpj_db,
    get_empresa_by_cnpj_db,
    patch_empresa_db
)
from service.sinteses import get_empresa_sintese_by_cnpj
from dependencies.db import get_db
from dependencies.user import get_current_user_id

router = APIRouter()

@router.get("", tags=["Empresas"])
def listar_empresas(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return get_all_empresas_db(db, user_id)


@router.get("/{cnpj}", tags=["Empresas"])
def consultar_empresa(cnpj: str, db: Session = Depends(get_db)):
    return get_empresa_by_cnpj_db(db, cnpj)

@router.post("/cadastro", tags=["Empresas"])
async def cadastrar_empresa(
    empresa: EmpresaSchema,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    return await create_empresa_db(db, empresa, background_tasks, user_id)

@router.patch("/{cnpj}", tags=["Empresas"])
def atualizar_empresa(
    cnpj: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    return patch_empresa_db(db, cnpj, payload)

@router.delete("/delete", tags=["Empresas"])
def deletar_empresa(
    cnpj: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    return delete_empresa_by_cnpj_db(db, cnpj, user_id)

@router.get("/{cnpj}/sintese", tags=["Empresas"])
async def obter_sintese_empresa(
    cnpj: str,
    force_update: bool = Query(False, description="Forçar atualização da síntese"),
    db: Session = Depends(get_db)
):
    return await get_empresa_sintese_by_cnpj(db, cnpj, force_update)
