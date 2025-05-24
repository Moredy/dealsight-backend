from pydantic import BaseModel
from typing import List, Optional
from datetime import date

class SocioSchema(BaseModel):
    nome: str
    cargo: str
    desde: date

class EmpresaSchema(BaseModel):
    cnpj: str
    nome_fantasia: Optional[str] = None

