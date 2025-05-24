from fastapi import APIRouter, Depends, UploadFile, File, Form, Body, Request,HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List, Optional, Any

from service.replanilhamento import (
    obter_historico_por_cnpj_db,
    replanilhamento_db,
    json_para_excel_db,
replanilhamento_status_db,
reclassificar_balanco_db
)
from dependencies.db import get_db
from dependencies.user import get_current_user_id

router = APIRouter()

@router.get("/status/{request_id}")
async def get_status(request_id: str, db: Session = Depends(get_db)):
    return await replanilhamento_status_db(request_id, db)

# ----- Faturamento -----

@router.post("/faturamento", tags=["Replanilhamento - Faturamento"])
async def replanilhar_faturamento(
    files: List[UploadFile] = File(...),
    user_id: int = Depends(get_current_user_id),
    cnpj: str = Form(...),
    db: Session = Depends(get_db)
):
    return await replanilhamento_db(files, user_id, cnpj, 'faturamento', db)

@router.get("/faturamento/historico/{cnpj}", tags=["Replanilhamento - Faturamento"])
async def historico_faturamento(
    cnpj: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    return await obter_historico_por_cnpj_db(cnpj, user_id, 'faturamento', db)

@router.post("/faturamento/gerar-excel", tags=["Replanilhamento - Faturamento"])
async def gerar_excel_faturamento(json: Dict = Body(...)):
    return json_para_excel_db(json, 'faturamento')

# ----- Endividamento -----

@router.get("/endividamento/historico/{cnpj}", tags=["Replanilhamento - Endividamento"])
async def historico_endividamento(
    cnpj: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    return await obter_historico_por_cnpj_db(cnpj, user_id, 'endividamento', db)

@router.post("/endividamento", tags=["Replanilhamento - Endividamento"])
async def replanilhar_endividamento(
    files: List[UploadFile] = File(...),
    user_id: int = Depends(get_current_user_id),
    cnpj: str = Form(...),
    db: Session = Depends(get_db)
):
    return await replanilhamento_db(files, user_id, cnpj, 'endividamento', db)

@router.post("/endividamento/gerar-excel", tags=["Replanilhamento - Endividamento"])
async def gerar_excel_endividamento(json: Dict = Body(...)):
    return json_para_excel_db(json, 'endividamento')

# Balanço

@router.get("/balanco/historico/{cnpj}", tags=["Replanilhamento - Balanco"])
async def historico_balanco(
    cnpj: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    return await obter_historico_por_cnpj_db(cnpj, user_id, 'balanco', db)

@router.post("/balanco", tags=["Replanilhamento - Endividamento"])
async def replanilhar_balanco(
    files: List[UploadFile] = File(...),
    user_id: int = Depends(get_current_user_id),
    cnpj: str = Form(...),
    prompt: Optional[str] = Form(None),  # Aqui está opcional
    db: Session = Depends(get_db)
):
    return await replanilhamento_db(files, user_id, cnpj, 'balanco',  db, prompt)


@router.post("/balanco/reclassificar")
async def reclassificar_balanco(request: Request):
    try:
        body: Dict[str, Any] = await request.json()

        prompt = body.get("prompt")
        current_classification = body.get("currentClassification")

        if prompt is None:
            raise HTTPException(status_code=400, detail="Campo 'prompt' é obrigatório.")

        return await reclassificar_balanco_db(current_classification, prompt)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar requisição: {str(e)}")

@router.post("/balanco/gerar-excel", tags=["Replanilhamento - Balanco"])
async def gerar_excel_endividamento(json: Dict = Body(...)):
    return json_para_excel_db(json, 'balanco')