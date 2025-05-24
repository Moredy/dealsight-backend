from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict
from sqlalchemy import select
from sqlalchemy.orm import aliased
from model.models import Aviso, Empresa, Monitoramento, User, OrganizacaoEmpresa
from fastapi import HTTPException
from datetime import datetime, timedelta

from datetime import datetime, timedelta

async def listar_avisos_por_cnpj_db(db, cnpj: str):
    try:
        # Buscar empresa
        result_empresa = db.execute(
            select(Empresa).where(Empresa.cnpj == cnpj)
        )
        empresa = result_empresa.scalar_one_or_none()
        if not empresa:
            return []

        # Buscar monitoramentos da empresa
        result_monitoramentos = db.execute(
            select(Monitoramento.id).where(Monitoramento.empresa_id == empresa.id)
        )
        monitoramento_ids = [row[0] for row in result_monitoramentos.fetchall()]

        if not monitoramento_ids:
            return []

        # Filtrar avisos apenas do dia atual
        hoje = datetime.now().date()
        inicio_dia = datetime.combine(hoje, datetime.min.time())
        fim_dia = datetime.combine(hoje, datetime.max.time())

        Mon = aliased(Monitoramento)

        stmt = (
            select(Aviso, Mon.modulo)
            .join(Mon, Aviso.modulo_associado_id == Mon.id)
            .where(
                Aviso.modulo_associado_id.in_(monitoramento_ids),
                Aviso.criado_em >= inicio_dia,
                Aviso.criado_em <= fim_dia
            )
            .order_by(Aviso.nivel_importancia.desc(), Aviso.criado_em.desc())
        )

        result = db.execute(stmt)
        rows = result.fetchall()

        # Filtrar avisos com classe_aviso distintas
        avisos_com_modulo = []
        classes_vistas = set()

        for aviso, modulo_nome in rows:
            if aviso.classe_aviso in classes_vistas:
                continue
            classes_vistas.add(aviso.classe_aviso)

            aviso_dict = aviso.__dict__.copy()
            aviso_dict.pop("_sa_instance_state", None)
            aviso_dict.pop("modulo_associado_id", None)
            aviso_dict["modulo"] = modulo_nome
            avisos_com_modulo.append(aviso_dict)

        return avisos_com_modulo

    except Exception as e:
        db.rollback()
        raise e




async def listar_todos_avisos_db(db, user_id: int) -> List[Dict]:
    # Recupera o usuário e sua organização
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.organizacao_id:
        raise HTTPException(status_code=400, detail="Usuário sem organização vinculada.")

    # Aliases
    Mon = aliased(Monitoramento)
    Emp = aliased(Empresa)
    OrgEmp = aliased(OrganizacaoEmpresa)

    # Query para buscar apenas avisos de empresas da organização do usuário
    stmt = (
        select(Aviso, Mon.modulo, Emp)
        .join(Mon, Aviso.modulo_associado_id == Mon.id)
        .join(Emp, Mon.empresa_id == Emp.id)
        .join(OrgEmp, OrgEmp.empresa_id == Emp.id)
        .where(OrgEmp.organizacao_id == user.organizacao_id)
        .order_by(Aviso.criado_em.desc())
    )

    result = db.execute(stmt)
    rows = result.fetchall()

    avisos_completos = []
    for aviso, modulo_nome, empresa in rows:
        aviso_dict = aviso.__dict__.copy()
        aviso_dict.pop("_sa_instance_state", None)
        aviso_dict.pop("modulo_associado_id", None)
        aviso_dict["modulo"] = modulo_nome
        aviso_dict["mensagem"] = getattr(aviso, "mensagem", None)

        empresa_dict = empresa.__dict__.copy()
        empresa_dict.pop("_sa_instance_state", None)

        aviso_dict["empresa"] = empresa_dict
        avisos_completos.append(aviso_dict)

    return avisos_completos