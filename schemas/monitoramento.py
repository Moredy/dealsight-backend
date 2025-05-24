from pydantic import BaseModel
from typing import List, Optional
from datetime import date


class MonitoramentoBaseSchema(BaseModel):
    modulo: Optional[str] = None
    frequencia: Optional[str] = None