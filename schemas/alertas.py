from pydantic import BaseModel
from typing import Optional

class AlertaCreateSchema(BaseModel):
    module_name: str
    contact_method: str
    indice_min: float