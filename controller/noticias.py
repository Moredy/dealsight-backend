from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from datetime import date

from schemas.noticias import NewsScrapperSchema, GetNewsSchema, PalavraChaveCreateSchema
from service.noticias import (
    buscar_noticias_db,
    buscar_e_salvar_noticias_db,
    consultar_noticias_db,
    criar_palavra_chave_db,
    listar_palavras_chave_db,
    deletar_palavra_chave_db,
    calcular_indice_risco_db
)
from dependencies.db import get_db

router = APIRouter()

# Notícias — scraping
@router.post("/consulta", tags=["Notícias"])
async def buscar_noticias(data: NewsScrapperSchema, db: Session = Depends(get_db)):
    return await buscar_noticias_db(db, data)

@router.post("/cadastro", tags=["Notícias"])
async def buscar_e_salvar_noticias(data: NewsScrapperSchema, db: Session = Depends(get_db)):
    return await buscar_e_salvar_noticias_db(db, data)

@router.get("/consulta-db", tags=["Notícias"])
async def consultar_noticias(data: GetNewsSchema = Depends(), db: Session = Depends(get_db)):
    return await consultar_noticias_db(db, data)

# Palavras-chave
@router.post("/criar-palavra", tags=["Notícias"])
def criar_palavra(data: PalavraChaveCreateSchema, db: Session = Depends(get_db)):
    return criar_palavra_chave_db(db, data)

@router.get("/palavras-chave", tags=["Notícias"])
def listar_palavras_chave(cnpj: str, db: Session = Depends(get_db)):
    return listar_palavras_chave_db(db, cnpj)

@router.delete("/delete-palavra-chave", tags=["Notícias"])
def deletar_palavra_chave(palavra_id: int, db: Session = Depends(get_db)):
    sucesso = deletar_palavra_chave_db(db, palavra_id)
    if not sucesso:
        raise HTTPException(status_code=404, detail="Palavra-chave não encontrada")
    return {"detail": "Palavra-chave deletada com sucesso"}

# Desempenho / Risco
@router.get("/desempenho/{cnpj}", tags=["Notícias"])
def calcular_indice_risco(
    cnpj: str,
    data_inicio: date = Query(..., description="Data inicial no formato YYYY-MM-DD"),
    data_fim: date = Query(..., description="Data final no formato YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    return calcular_indice_risco_db(db, cnpj, data_inicio, data_fim)
