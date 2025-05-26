
from fastapi import HTTPException, Request
import httpx
from datetime import timedelta

from service.protestos import consultar_gravar_protestos_por_cnpj_db
from schemas.monitoramento import MonitoramentoBaseSchema
from model.models import Empresa, Socio, Monitoramento, Noticia, Processo, DividaAtivaUniao, DividaAtivaSp, BuildStatusModel
from service.noticias import buscar_e_salvar_noticias_db
from datetime import datetime
import time
from sqlalchemy.orm import joinedload
from database import SessionLocal
from datetime import date, timedelta
from service.noticias import listar_palavras_chave_db
from schemas.noticias import NewsScrapperSchema  # ajuste o import conforme sua estrutura
from service.divida_ativa_sp import buscar_salvar_divida_ativa_sp_db, verificar_e_criar_aviso_divida_ativa_sp
from service.divida_ativa_uniao import buscar_salvar_divida_ativa_uniao_db, verificar_e_criar_aviso_divida_ativa_uniao
from service.juridico import adicionar_fila_analise_db, verificar_e_criar_aviso_variacao_processos
from service.valor_economico import buscar_salvar_dados_valor_economico_db , verificar_e_criar_aviso_movimentacoes_falimentares
from service.juridico import buscar_processos_jusfy_e_salvar_db, verificar_variacao_indice_risco_juridico
from service.noticias import verificar_e_criar_aviso_noticias

def get_desempenho_monitoramento(cnpj: str, db):
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()

    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    results = []

    three_days_ago = datetime.now() - timedelta(days=3)

    # Query and calculate weighted score for Noticias
    noticias = db.query(Empresa, Noticia).join(Noticia).filter(
        Empresa.id == empresa.id,
        Noticia.published >= three_days_ago
    ).order_by(Noticia.published.desc()).all()
    for _, noticia in noticias:
        weighted_score = noticia.risc * noticia.relevance
        results.append({
            "module": "noticias",
            "risk": noticia.risc,
            "relevance": noticia.relevance,
            "description": noticia.description,
            "date": noticia.published,
            "weighted_score": weighted_score
        })

    # Query and calculate weighted score for Processos
    processos = db.query(Empresa, Processo).join(Processo).filter(
        Empresa.id == empresa.id,
        Processo.data_distribuicao >= three_days_ago
    ).order_by(Processo.data_distribuicao.desc()).all()
    for _, processo in processos:
        weighted_score = processo.risc * processo.relevance
        results.append({
            "module": "juridico",
            "risk": processo.risc,
            "relevance": processo.relevance,
            "description": processo.description,
            "date": processo.data_distribuicao,
            "weighted_score": weighted_score
        })

    # Query and calculate weighted score for DividaAtivaUniao
    dividas_uniao = db.query(Empresa, DividaAtivaUniao).join(DividaAtivaUniao).filter(
        Empresa.id == empresa.id,
        DividaAtivaUniao.data_consulta >= three_days_ago
    ).order_by(DividaAtivaUniao.data_consulta.desc()).all()
    for _, divida in dividas_uniao:
        weighted_score = divida.risco * divida.relevancia
        results.append({
            "module": "dividas_uniao",
            "risk": divida.risco,
            "relevance": divida.relevancia,
            "description": divida.descricao,
            "date": divida.data_consulta,
            "weighted_score": weighted_score
        })

    # Query and calculate weighted score for DividaAtivaSp
    dividas_sp = db.query(Empresa, DividaAtivaSp).join(DividaAtivaSp).filter(
        Empresa.id == empresa.id,
        DividaAtivaSp.data_consulta >= three_days_ago
    ).order_by(DividaAtivaSp.data_consulta.desc()).all()
    for _, divida in dividas_sp:
        weighted_score = divida.risco * divida.relevancia
        results.append({
            "module": "dividas_sp",
            "risk": divida.risco,
            "relevance": divida.relevancia,
            "description": divida.descricao,
            "date": divida.data_consulta,
            "weighted_score": weighted_score
        })

    # Sort results by weighted score in descending order
    results.sort(key=lambda x: x["weighted_score"], reverse=True)

    # Remove weighted_score from the final output
    for result in results:
        result.pop("weighted_score")

    return results

def get_monitoramento_db(cnpj: str, modulo_name:str, db):
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    monitoramento = db.query(Monitoramento).filter(Monitoramento.empresa_id == empresa.id,
        Monitoramento.modulo == modulo_name).first()
    if not monitoramento:
        raise HTTPException(status_code=404, detail="Monitoramento não encontrado")

    return monitoramento

def update_monitoramento_db(cnpj: str, update_data: MonitoramentoBaseSchema, db):
    from fastapi import HTTPException

    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    if not update_data.modulo:
        raise HTTPException(status_code=400, detail="Campo 'modulo' é obrigatório para atualizar o monitoramento")

    monitoramento = db.query(Monitoramento).filter(
        Monitoramento.empresa_id == empresa.id,
        Monitoramento.modulo == update_data.modulo
    ).first()

    if not monitoramento:
        raise HTTPException(status_code=404, detail=f"Monitoramento do módulo '{update_data.modulo}' não encontrado")

    # Atualiza apenas os campos enviados
    if update_data.frequencia is not None:
        monitoramento.frequencia = update_data.frequencia

    db.commit()
    db.refresh(monitoramento)
    return monitoramento


async def cron_cadastrar_avisos_empresa_db(cnpj: str):
    db = SessionLocal()
    try:

        empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()

        if not empresa:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")

        modulos_ativos_db = db.query(Monitoramento).filter(
            Monitoramento.empresa_id == empresa.id,
        )

        modulos_ativos = [modulo.modulo for modulo in modulos_ativos_db]


        if empresa.monitoramento_ativo:
            if "juridico" in modulos_ativos:
                try:
                    esferas_processuais = [
                        'penais',
                        'trabalhistas',
                        'fiscais',
                        'administrativas',
                        'eleitorais',
                        'militares',
                        'civis'
                    ]

                    for esfera in esferas_processuais:
                        await verificar_e_criar_aviso_variacao_processos(db, cnpj, esfera)

                    await verificar_variacao_indice_risco_juridico(db,cnpj)

                except Exception as e:
                    print(f"Erro ao executar verificação de variacao 'juridico': {e}")

            if "noticias" in modulos_ativos:
                try:
                    await verificar_e_criar_aviso_noticias(db, cnpj)
                except Exception as e:
                    print(f"Erro ao executar verificação de variacao 'noticias': {e}")

            if "divida-ativa-sp" in modulos_ativos:
                try:
                    await verificar_e_criar_aviso_divida_ativa_sp(db, cnpj)
                except Exception as e:
                    print(f"Erro ao executar verificação de variacao 'divida-ativa-sp': {e}")

            if "divida-ativa-uniao" in modulos_ativos:
                try:
                    await verificar_e_criar_aviso_divida_ativa_uniao(db, cnpj)
                except Exception as e:
                    print(f"Erro ao executar verificação de variacao 'divida-ativa-uniao': {e}")


            if "movimentacoes-falimentares" in modulos_ativos:
                try:
                    await verificar_e_criar_aviso_movimentacoes_falimentares(db, cnpj)
                except Exception as e:
                    print(f"Erro ao executar verificação de variacao 'movimentacoes_falimentares': {e}")



    finally:
        db.close()
    return {"message" : "Dados salvos com sucesso"}

async def cron_cadastrar_dados_empresa_db(cnpj: str):
    db = SessionLocal()

    def atualizar_status_modulo(
            db,
            request_id: str,
            status: str,
            progress: int = 100,
            erro: str | None = None
    ):
        build_status = db.query(BuildStatusModel).filter_by(request_id=request_id).first()
        if build_status:
            build_status.status = status
            build_status.progress = progress
            build_status.end_time = datetime.utcnow()
            build_status.updated_at = datetime.utcnow()

            if erro:
                if not build_status.errors:
                    build_status.errors = []
                build_status.errors.append(erro)

            db.commit()

    try:
        # Salva sempre do dia anterior e atual
        hoje = date.today()
        tres_meses_atras = hoje - timedelta(days=90)


        empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()

        if not empresa:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")

        modulos_ativos_db = db.query(Monitoramento).filter(
            Monitoramento.empresa_id == empresa.id,
        )

        modulos_ativos = [{"id": modulo.id, "modulo": modulo.modulo} for modulo in modulos_ativos_db]
        modulos_ativos_nomes = [m["modulo"] for m in modulos_ativos]

        palavras_chave_db = listar_palavras_chave_db(db, cnpj)

        palavras_chave = [linha.texto for linha in palavras_chave_db]

        newsSchema = NewsScrapperSchema(
            cnpj=cnpj,
            data_inicio=tres_meses_atras,
            data_fim=hoje,
            nao_incluir_nome_empresa_palavra_chave=False,
            palavras_chave=palavras_chave,
            limite_noticias=50
        )

        modulo_request_ids = {}

        if empresa.monitoramento_ativo:
            for i, modulo in enumerate(modulos_ativos):
                request_id = f"{cnpj}_{int(time.time())}_{i}"

                build_status = BuildStatusModel(
                    status="pendente",
                    progress=0,
                    request_id=request_id,
                    start_time=datetime.utcnow(),
                    end_time=None,
                    errors=[],
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    monitoramento_id=int(modulo["id"])
                )

                modulo_request_ids[modulo["modulo"]] = request_id
                db.add(build_status)

            db.commit()

            if "noticias" in modulos_ativos_nomes:
                try:
                    print("Executando código para módulo 'noticias'")
                    await buscar_e_salvar_noticias_db(db, newsSchema)
                    atualizar_status_modulo(db, modulo_request_ids["noticias"], "concluído")
                except Exception as e:
                    print(f"Erro ao executar módulo 'noticias': {e}")
                    atualizar_status_modulo(db, modulo_request_ids["noticias"], "erro", erro=str(e))

            if "divida-ativa-uniao" in modulos_ativos_nomes:
                try:
                    await buscar_salvar_divida_ativa_uniao_db(db, cnpj)
                    atualizar_status_modulo(db, modulo_request_ids["divida-ativa-uniao"], "concluído")
                except Exception as e:
                    print(f"Erro ao executar módulo 'divida-ativa-uniao': {e}")
                    atualizar_status_modulo(db, modulo_request_ids["divida-ativa-uniao"], "erro", erro=str(e))

            if "divida-ativa-sp" in modulos_ativos_nomes:
                try:
                    await buscar_salvar_divida_ativa_sp_db(db, cnpj)
                    atualizar_status_modulo(db, modulo_request_ids["divida-ativa-sp"], "concluído")
                except Exception as e:
                    print(f"Erro ao executar módulo 'divida-ativa-sp': {e}")
                    atualizar_status_modulo(db, modulo_request_ids["divida-ativa-sp"], "erro", erro=str(e))

            if "juridico" in modulos_ativos_nomes:
                try:
                    # Será necessário outro cron para salvar os dados na db
                    await adicionar_fila_analise_db(db, cnpj)

                    esferas_processuais = [
                        'penais',
                        'trabalhistas',
                        'fiscais',
                        'administrativas',
                        'eleitorais',
                        'militares',
                        'civis'
                    ]

                    for esfera in esferas_processuais:
                        await verificar_e_criar_aviso_variacao_processos(db, cnpj, esfera)

                except Exception as e:
                    print(f"Erro ao executar módulo 'juridico': {e}")
                    atualizar_status_modulo(db, modulo_request_ids["juridico"], "erro", erro=str(e))

            if "movimentacoes-falimentares" in modulos_ativos_nomes:
                try:
                    await buscar_salvar_dados_valor_economico_db(db)
                    atualizar_status_modulo(db, modulo_request_ids["movimentacoes-falimentares"], "concluído")
                except Exception as e:
                    print(f"Erro ao executar módulo 'movimentacoes-falimentares': {e}")
                    atualizar_status_modulo(db, modulo_request_ids["movimentacoes-falimentares"], "erro", erro=str(e))

            if "protestos" in modulos_ativos_nomes:
                try:
                    await consultar_gravar_protestos_por_cnpj_db(cnpj, db)
                    atualizar_status_modulo(db, modulo_request_ids["protestos"], "concluído")
                except Exception as e:
                    print(f"Erro ao executar módulo 'protestos': {e}")
                    atualizar_status_modulo(db, modulo_request_ids["protestos"], "erro", erro=str(e))

    finally:
        db.close()
    return {"message" : "Dados salvos com sucesso"}

async def cron_cadastrar_processos_empresa_db(cnpj: str):
    db = SessionLocal()
    try:
        # Analisa apenas dos ultimos 3 dias, mas sempre puxa tudo, existe um limite de 30 analises
        hoje = date.today()
        ultimos_meses = hoje - timedelta(days=3)

        hoje_formatado = hoje.strftime("%Y-%m-%d")
        ultimos_meses_formatado = ultimos_meses.strftime("%Y-%m-%d")


        empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()

        if not empresa:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")

        modulos_ativos_db = db.query(Monitoramento).filter(
            Monitoramento.empresa_id == empresa.id,
        )

        modulos_ativos = [modulo.modulo for modulo in modulos_ativos_db]


        if "juridico" in modulos_ativos:
            build_status = (
                db.query(BuildStatusModel)
                .join(Monitoramento)
                .filter(Monitoramento.empresa_id == empresa.id)
                .filter(Monitoramento.modulo == "juridico")
                .order_by(BuildStatusModel.created_at.desc())
                .first()
            )

            try:
                await buscar_processos_jusfy_e_salvar_db(db, cnpj, ultimos_meses_formatado, hoje_formatado)

                if build_status:
                    build_status.status = "concluído"
                    build_status.progress = 100
                    build_status.end_time = datetime.utcnow()
                    build_status.updated_at = datetime.utcnow()
                    db.commit()

            except Exception as e:
                print(f"[Erro juridico] {e}")
                db.rollback()
                if build_status:
                    build_status.status = "erro"
                    build_status.errors.append(str(e))
                    build_status.end_time = datetime.utcnow()
                    build_status.updated_at = datetime.utcnow()
                    db.commit()

    finally:
        db.close()
    return {"message" : "Dados salvos com sucesso"}

def get_ultimo_status_modulo_db(cnpj: str, modulo: str, db):
    # Buscar a empresa
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    # Buscar o monitoramento correspondente ao módulo
    monitoramento = db.query(Monitoramento).filter(
        Monitoramento.empresa_id == empresa.id,
        Monitoramento.modulo == modulo
    ).first()

    if not monitoramento:
        raise HTTPException(status_code=404, detail="Módulo não encontrado para essa empresa")

    # Buscar o último status
    build_status = db.query(BuildStatusModel).filter(
        BuildStatusModel.monitoramento_id == monitoramento.id
    ).order_by(BuildStatusModel.created_at.desc()).first()

    if not build_status:
        raise HTTPException(status_code=404, detail="Nenhum status encontrado para esse módulo")

    # Função que converte UTC para horário de Brasília (UTC-3)
    def to_brasilia(dt):
        return dt - timedelta(hours=3) if dt else None

    return {
        "request_id": build_status.request_id,
        "status": build_status.status,
        "progress": build_status.progress,
        "start_time": to_brasilia(build_status.start_time),
        "end_time": to_brasilia(build_status.end_time),
        "errors": build_status.errors,
        "created_at": to_brasilia(build_status.created_at),
        "updated_at": to_brasilia(build_status.updated_at),
    }

async def executar_cron_para_todas_empresas(db):
    empresas = db.query(Empresa).all()

    for empresa in empresas:
        try:
            print(f"Processando empresa {empresa.nome} - CNPJ: {empresa.cnpj}")
            await cron_cadastrar_dados_empresa_db(empresa.cnpj)
        except Exception as e:
            print(f"Erro ao processar a empresa {empresa.cnpj}: {e}")

async def executar_cron_para_todas_avisos_empresas(db):
    empresas = db.query(Empresa).all()

    for empresa in empresas:
        try:
            print(f"Processando avisos da empresa {empresa.nome} - CNPJ: {empresa.cnpj}")
            await cron_cadastrar_avisos_empresa_db(empresa.cnpj)
        except Exception as e:
            print(f"Erro ao processar a empresa {empresa.cnpj}: {e}")


async def executar_cron_para_todas_processos_empresas(db):
    empresas = db.query(Empresa).all()

    for empresa in empresas:
        if empresa.monitoramento_ativo:
            try:
                print(f"Processando empresa {empresa.nome} - CNPJ: {empresa.cnpj}")
                await cron_cadastrar_processos_empresa_db(empresa.cnpj)
            except Exception as e:
                print(f"Erro ao processar o juridico da {empresa.cnpj}: {e}")