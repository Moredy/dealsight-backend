from pydantic import BaseModel
from typing import Optional
from datetime import date

class SinteseSchema(BaseModel):
    texto: str
    data_criacao: date
    empresa_id: int

class SinteseResponseSchema(BaseModel):
    id: int
    empresa_id: int
    texto: str
    data_criacao: date
    dias_desde_atualizacao: int 