from pydantic import BaseModel
from typing import List, Optional
from datetime import date


class NewsScrapperSchema(BaseModel):
    cnpj: str
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None
    nao_incluir_nome_empresa_palavra_chave: Optional[bool] = False
    palavras_chave: List[str] = []
    limite_noticias: Optional[int] = 50

class GetNewsSchema(BaseModel):
    cnpj: str
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None

#Palavras chave
class PalavraChaveCreateSchema(BaseModel):
    texto: str
    cnpj: str