from sqlalchemy.orm import Session
from model.models import Empresa, Alerta
from schemas.alertas import AlertaCreateSchema

def criar_alerta_db(db: Session, empresa_cnpj: str, data: AlertaCreateSchema):
    empresa = db.query(Empresa).filter(Empresa.cnpj == empresa_cnpj).first()
    if not empresa:
        return None

    alerta = Alerta(
        empresa_id=empresa.id,
        module_name=data.module_name,
        contact_method=data.contact_method,
        indice_min=data.indice_min,
    )

    db.add(alerta)
    db.commit()
    db.refresh(alerta)
    return alerta

def listar_alertas_db(db: Session, empresa_cnpj: str):
    empresa = db.query(Empresa).filter(Empresa.cnpj == empresa_cnpj).first()
    if not empresa:
        return None

    return db.query(Alerta).filter(Alerta.empresa_id == empresa.id).all()

def deletar_alerta_db(db: Session, alerta_id: int):
    alerta = db.query(Alerta).filter(Alerta.id == alerta_id).first()
    if not alerta:
        return False

    db.delete(alerta)
    db.commit()
    return True
