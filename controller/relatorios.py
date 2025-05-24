from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Literal
import re
from sqlalchemy.orm import Session
from dependencies.db import get_db
router = APIRouter()
from service.relatorios import gerar_relatorio_db
from dependencies.user import get_current_user_id
from typing import Dict
import re


@router.get("/gerar-relatorio")
async def gerar_relatorio_por_periodo(
        tipo_relatorio: Literal["relatorio-analise-credito"],
        mes_inicio: str = Query(..., example="01/2024"),
        mes_fim: str = Query(..., example="12/2024"),
        cnpj: str = Query(..., example="12345678000199"),
        user_id: int = Depends(get_current_user_id),
        db: Session = Depends(get_db)
):
    # Validação básica do CNPJ
    if not re.fullmatch(r"\d{14}", cnpj):
        raise HTTPException(status_code=400, detail="CNPJ inválido. Use 14 dígitos numéricos.")

    # Validação do formato mm/yyyy
    def validar_mes_formatado(mes: str):
        return re.fullmatch(r"(0[1-9]|1[0-2])/20\d{2}", mes)

    if not validar_mes_formatado(mes_inicio) or not validar_mes_formatado(mes_fim):
        raise HTTPException(status_code=400, detail="Formato dos meses deve ser mm/yyyy.")

    # Aqui você implementa a lógica para gerar o relatório
    return await gerar_relatorio_db(tipo_relatorio, mes_inicio, mes_fim, cnpj,user_id,db)


