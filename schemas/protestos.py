from pydantic import BaseModel
from datetime import datetime
from typing import Any

class ProtestoData(BaseModel):
    json_consulta_cenprot: Any
    cnpj: str