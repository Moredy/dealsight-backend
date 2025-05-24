from pydantic import BaseModel
from typing import List, Optional
from datetime import date


class GetProcessosSchema(BaseModel):
    cnpj: str
    data_inicio: date
    data_fim: date