from agents import Agent, Runner 
from fastapi import HTTPException, Request
import httpx
from schemas.empresas import EmpresaSchema
from model.models import Empresa, Socio, Monitoramento, Sintese,PalavraChave, Aviso,OrganizacaoEmpresa, Organizacao,User
from datetime import datetime, timedelta, date
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from fastapi import BackgroundTasks
import os
from service.monitoramento import cron_cadastrar_dados_empresa_db
from service.sinteses import _generate_empresa_sintese
API_CNPJ_URL = "https://open.cnpja.com/office"

async def create_empresa_db(db, empresa_data: EmpresaSchema, background_tasks: BackgroundTasks, user_id: int):
    # Recupera o usuário e sua organização
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.organizacao_id:
        raise HTTPException(status_code=400, detail="Usuário sem organização vinculada.")

    # Verifica se a empresa já está cadastrada
    existing = db.query(Empresa).filter(Empresa.cnpj == empresa_data.cnpj).first()
    if existing:
        # Verifica se a organização já está vinculada à empresa
        already_linked = db.query(OrganizacaoEmpresa).filter_by(
            organizacao_id=user.organizacao_id,
            empresa_id=existing.id
        ).first()

        if already_linked:
            raise HTTPException(status_code=400, detail="Empresa já cadastrada e vinculada à sua organização.")

        # Associa a organização à empresa existente
        nova_relacao = OrganizacaoEmpresa(
            organizacao_id=user.organizacao_id,
            empresa_id=existing.id
        )
        db.add(nova_relacao)
        db.commit()
        return existing

    # Se não existir, segue fluxo normal de criação
    try:
        response = httpx.get(f"{API_CNPJ_URL}/{empresa_data.cnpj}", timeout=10)
        response.raise_for_status()
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Erro ao acessar API externa: {e}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=500, detail=f"Erro na resposta da API externa: {e.response.status_code}")

    try:
        graph_response = httpx.post(
            f"{os.getenv('MS_GRAPH_API_URL')}/graph/build",
            json={"cnpj": empresa_data.cnpj},
            timeout=30
        )
        graph_response.raise_for_status()
    except Exception as e:
        print(f"Erro ao construir grafo para CNPJ {empresa_data.cnpj}: {str(e)}")

    data = response.json()

    nome = data.get("company", {}).get("name") or data.get("alias")
    atividade = data.get("mainActivity", {}).get("text")
    atividade_id = data.get("mainActivity", {}).get("id")

    if not nome:
        raise HTTPException(status_code=400, detail="Nome da empresa não encontrado na API externa")

    nova_empresa = Empresa(
        nome=nome,
        cnpj=empresa_data.cnpj,
        nome_fantasia=empresa_data.nome_fantasia,
        atividade_principal=atividade,
        atividade_principal_id=atividade_id,
    )

    # Sócios
    for membro in data.get("company", {}).get("members", []):
        pessoa = membro.get("person", {})
        role = membro.get("role", {})
        desde = membro.get("since")

        novo_socio = Socio(
            nome=pessoa.get("name"),
            cargo=role.get("text"),
            desde=datetime.fromisoformat(desde) if desde else None
        )
        nova_empresa.socios.append(novo_socio)

    # Adiciona a empresa e associa à organização do usuário
    db.add(nova_empresa)
    db.commit()
    db.refresh(nova_empresa)

    nova_relacao = OrganizacaoEmpresa(
        organizacao_id=user.organizacao_id,
        empresa_id=nova_empresa.id
    )
    db.add(nova_relacao)

    # Monitoramentos
    db.add_all([
        Monitoramento(modulo="noticias", frequencia="diario", empresa_id=nova_empresa.id),
        Monitoramento(modulo="juridico", frequencia="diario", empresa_id=nova_empresa.id),
        Monitoramento(modulo="divida-ativa-uniao", frequencia="diario", empresa_id=nova_empresa.id),
        Monitoramento(modulo="movimentacoes-falimentares", frequencia="diario", empresa_id=nova_empresa.id),
        Monitoramento(modulo="protestos", frequencia="diario", empresa_id=nova_empresa.id)
    ])

    if data['address']['state'] == 'SP':
        db.add(Monitoramento(modulo="divida-ativa-sp", frequencia="diario", empresa_id=nova_empresa.id))

    db.commit()

    if empresa_data.nome_fantasia:
        db.add(PalavraChave(texto=empresa_data.nome_fantasia, empresa_id=nova_empresa.id))
        db.commit()
    
    # Gera síntese para a nova empresa
    await _generate_empresa_sintese(db, nova_empresa.id)

    background_tasks.add_task(cron_cadastrar_dados_empresa_db, nova_empresa.cnpj)

    return nova_empresa


def get_all_empresas_db(db, user_id: int):
    # Recupera a organização associada ao usuário
    user = db.query(User).filter(User.id == user_id).first()

    if not user or not user.organizacao_id:
        raise HTTPException(status_code=404, detail="Usuário não vinculado a uma organização.")

    # Recupera as empresas vinculadas à organização do usuário
    empresas = (
        db.query(Empresa)
        .join(OrganizacaoEmpresa, OrganizacaoEmpresa.empresa_id == Empresa.id)
        .filter(OrganizacaoEmpresa.organizacao_id == user.organizacao_id)
        .options(joinedload(Empresa.socios))
        .all()
    )

    if not empresas:
        raise HTTPException(status_code=404, detail="Nenhuma empresa encontrada para o usuário.")

    resultado = []
    tres_dias_atras = datetime.now() - timedelta(days=3)

    for empresa in empresas:
        monitoramento_ids = (
            db.query(Monitoramento.id)
            .filter(Monitoramento.empresa_id == empresa.id)
            .all()
        )
        monitoramento_ids = [id[0] for id in monitoramento_ids]

        quantidade_avisos = (
            db.query(func.count(func.distinct(Aviso.classe_aviso)))
            .filter(
                Aviso.modulo_associado_id.in_(monitoramento_ids),
                func.date(Aviso.criado_em) == date.today()
            )
            .scalar()
            if monitoramento_ids else 0
        )

        empresa_dict = empresa.__dict__.copy()
        empresa_dict["quantidade_avisos"] = quantidade_avisos
        empresa_dict.pop("_sa_instance_state", None)

        resultado.append(empresa_dict)

    return resultado

def get_empresa_by_cnpj_db(db, cnpj: str):
    empresa = db.query(Empresa).options(joinedload(Empresa.socios)).filter(Empresa.cnpj == cnpj).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    monitoramento_ids = db.query(Monitoramento.id).filter(Monitoramento.empresa_id == empresa.id).all()
    monitoramento_ids = [id[0] for id in monitoramento_ids]


    #Contar avisos do dia
    quantidade_avisos = (
        db.query(func.count(func.distinct(Aviso.classe_aviso)))
        .filter(
            Aviso.modulo_associado_id.in_(monitoramento_ids),
            func.date(Aviso.criado_em) == date.today()
        )
        .scalar()
        if monitoramento_ids else 0
    )

    empresa_dict = empresa.__dict__.copy()
    empresa_dict["quantidade_avisos"] = quantidade_avisos
    empresa_dict.pop("_sa_instance_state", None)

    return empresa_dict

def delete_empresa_by_cnpj_db(db, cnpj: str, user_id: int):
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()

    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    # Recupera a organização do usuário
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.organizacao_id:
        raise HTTPException(status_code=400, detail="Usuário não vinculado a nenhuma organização")

    # Verifica se a empresa está associada a outras organizações
    relacoes = db.query(OrganizacaoEmpresa).filter(OrganizacaoEmpresa.empresa_id == empresa.id).all()

    if not relacoes:
        raise HTTPException(status_code=400, detail="A empresa não está vinculada a nenhuma organização")

    if len(relacoes) > 1:
        # Apenas remove a relação com a organização do usuário
        relacao_do_usuario = db.query(OrganizacaoEmpresa).filter_by(
            empresa_id=empresa.id,
            organizacao_id=user.organizacao_id
        ).first()

        if relacao_do_usuario:
            db.delete(relacao_do_usuario)
            db.commit()
            return {"detail": f"Empresa desvinculada da sua organização (ID {user.organizacao_id}) com sucesso"}
        else:
            raise HTTPException(status_code=403, detail="Empresa não está vinculada à organização do usuário")
    else:
        # A empresa só está vinculada a essa organização → pode deletar a empresa inteira
        db.delete(empresa)
        db.commit()
        return {"detail": f"Empresa com CNPJ {cnpj} deletada com sucesso"}

def patch_empresa_db(db, cnpj: str, updates: dict):
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()

    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    # Atualiza apenas os campos presentes no payload
    for key, value in updates.items():
        if hasattr(empresa, key):
            setattr(empresa, key, value)

    db.commit()
    db.refresh(empresa)

    return {
        "detail": "Empresa atualizada com sucesso",
        "empresa": {
            "cnpj": empresa.cnpj,
            "nome": empresa.nome,
            "monitoramento_ativo": empresa.monitoramento_ativo,
            "nome_fantasia": empresa.nome_fantasia,
            "atividade_principal": empresa.atividade_principal,
            "atividade_principal_id": empresa.atividade_principal_id,
            # Adicione mais campos aqui conforme necessário
        }
    }