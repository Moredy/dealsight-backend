import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import threading
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from model.models import Empresa, Sintese
from agents import Agent, Runner
from openai import OpenAI

async def _generate_empresa_sintese(db: Session, empresa_id: int) -> Sintese:
    """
    Generate a new company summary using GPT and store it in the database.
    This function does the actual work of generating a new summary.
    """
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        raise HTTPException(status_code=404, detail=f"Empresa com ID {empresa_id} não encontrada")
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    input_prompt = f"""
    Você é um analista de empresas especializado em síntese de informações corporativas.
    Sua tarefa é criar uma síntese estruturada e bem elaborada sobre a empresa {empresa.nome} (CNPJ: {empresa.cnpj}).
    
    Utilize informações públicas disponíveis de fontes confiáveis para elaborar uma síntese que inclua:
    
    1. A descrição do negócio, setor e área de atuação;
    2. A posição competitiva da empresa e seus principais concorrentes;
    3. Os desafios e oportunidades atuais relacionados ao contexto econômico, regulatório ou setorial;
    4. As notícias recentes mais relevantes, especialmente aquelas que indicam riscos ou oportunidades estratégicas.
    
    A síntese deve ser estruturada, objetiva e baseada em fatos verificáveis.
    A síntese deve ser escrita em um texto dissertativo, com um único parágrafo.
    Não use negrito, nem itálico, nem sublinhado, nem coloração de texto ou emojis.
    Mantenha uma linguagem formal e profissional.
    """
    
    response = client.chat.completions.create(
        model="gpt-4o-mini-search-preview",
        messages=[
            {"role": "system", "content": input_prompt},
            {"role": "user", "content": "Síntese para a empresa {empresa.nome} (CNPJ: {empresa.cnpj})"}
        ]
    )
    
    result = response.choices[0].message.content
    
    nova_sintese = Sintese(
        empresa_id=empresa.id,
        texto=result,
        data_criacao=datetime.now(timezone.utc)
    )
    
    try:
        db.add(nova_sintese)
        db.commit()
        db.refresh(nova_sintese)
        return nova_sintese
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro ao salvar a síntese da empresa")

async def get_empresa_sintese(db: Session, empresa_id: int, force_update: bool = False) -> Dict[str, Any]:
    """
    Get the company summary, generating a new one if needed.
    
    Args:
        db: Database session
        empresa_id: ID of the company
        force_update: If True, force a new summary to be generated
        
    Returns:
        Dictionary with the summary and metadata
    """
    current_time = datetime.now(timezone.utc)
    
    latest_sintese = db.query(Sintese).filter(
        Sintese.empresa_id == empresa_id
    ).order_by(Sintese.data_criacao.desc()).first()
    
    update_needed = (
        force_update or 
        not latest_sintese or 
        (current_time.date() - latest_sintese.data_criacao).days > 15
    )
    
    print(f"Empresa {empresa_id} - update_needed: {update_needed}")
    
    if update_needed:
        latest_sintese = await _generate_empresa_sintese(db, empresa_id)
        
    result = {
        "id": latest_sintese.id,
        "empresa_id": latest_sintese.empresa_id,
        "texto": latest_sintese.texto,
        "data_criacao": latest_sintese.data_criacao,
        "dias_desde_atualizacao": (current_time.date() - latest_sintese.data_criacao).days
    }
    
    return result

async def get_empresa_sintese_by_cnpj(db: Session, cnpj: str, force_update: bool = False) -> Dict[str, Any]:
    """
    Get company summary by CNPJ instead of ID
    """
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()
    if not empresa:
        raise HTTPException(status_code=404, detail=f"Empresa com CNPJ {cnpj} não encontrada")
    
    return await get_empresa_sintese(db, empresa.id, force_update)
