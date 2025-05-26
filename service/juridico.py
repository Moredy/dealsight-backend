from agents import Agent, Runner  # Supondo que você já tenha essas classes
import json
import re
import httpx
from fastapi import HTTPException
from datetime import datetime
from sqlalchemy import func
from schemas.juridico import GetProcessosSchema
from model.models import Empresa, Processo, Sintese, ClassificacaoProcesso, Aviso, Monitoramento
from service.sinteses import get_empresa_sintese
from utils import get_process_sphere
from datetime import datetime,timedelta
from datetime import date
from sqlalchemy.future import select
from sqlalchemy import not_, and_
from typing import Optional
from datetime import date

API_JUSFY_LIST_QUERIES = "https://backend.jusfy.com.br/api/queries/list_queries?items_per_page=1000&page=1"
API_JUSFY_GET_PROCESSOS = "https://backend.jusfy.com.br/api/async_queries"
API_JUSFY_QUEUE_CNPJ = "https://backend.jusfy.com.br/api/queries/checkout"
TOKEN_JUSFY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6MTQ3NTUyLCJpYXQiOjE3NDY0NzM1MjcsImV4cCI6MTc0OTA2NTUyN30.xSEKjNQOSUSuwT-IKGq4EdYQCmuUG0hbOSN6gFA-mdM"

headersJusfy = {
    'Authorization': f'Bearer {TOKEN_JUSFY}',
}

async def adicionar_fila_analise_db(db, cnpj: str):

    # Verifica se empresa existe no banco
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()
    if not empresa:
        raise HTTPException(status_code=400, detail="Empresa não cadastrada.")

    body = {
        "document": cnpj,
        "product_selected": {
            "product_id": "lawsuit",
            "description": "Localize processos por CPF/CNPJ de forma fácil e rápida.",
            "name": "Buscador processual",
            "online": 1,
            "price": "0.00"
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                API_JUSFY_QUEUE_CNPJ,
                json=body,  # ← Usa 'json' ao invés de 'content'
                headers=headersJusfy
            )
            response.raise_for_status()
            return response.json()  # ← Retorna exatamente a resposta da API Jusfy

    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Erro ao acessar a API Jusfy: {e}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=500, detail=f"Erro na resposta da API Jusfy: {e.response.status_code}")


async def buscar_processos_jusfy_e_salvar_db(db, cnpj: str, data_inicio:str, data_fim: str):

    # Essas datas ditam a partir de onde e até onde a IA irá analisar
    data_inicio_date = datetime.strptime(data_inicio, "%Y-%m-%d").date()
    data_fim_date = datetime.strptime(data_fim, "%Y-%m-%d").date()

    def esta_no_intervalo(data_dist_, data_inicio_, data_fim_) -> bool:

        data_dist_date = datetime.strptime(data_dist_, "%Y-%m-%dT%H:%M:%S.%fZ").date()

        try:
            return data_inicio_ <= data_dist_date <= data_fim_
        except Exception as e:
            print(f"Erro ao converter data: {e}")
            return False


    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(API_JUSFY_LIST_QUERIES, headers=headersJusfy)
            response.raise_for_status()
            empresas_data = response.json()

        def limpar_cnpj(cnpj: str) -> str:
            return re.sub(r'\D', '', cnpj)  # remove tudo que não é dígito

        def get_empresa_id_by_cnpj(data, cnpj):
            processos = data.get("data", [])
            for process in processos:
                if limpar_cnpj(process.get("document")) == limpar_cnpj(cnpj):
                    return process.get("id")
            return None

        id_empresa_jusfy = get_empresa_id_by_cnpj(empresas_data, cnpj)

        if not id_empresa_jusfy:
            raise HTTPException(status_code=404, detail="Empresa não encontrada na base Jusfy.")

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_JUSFY_GET_PROCESSOS}/{id_empresa_jusfy}?page=1&page_size=20000", headers=headersJusfy)
            response.raise_for_status()
            processos_data = response.json()

        processos = processos_data.get("query_info", {}).get("provider_response", {}).get("parsedLawsuits", {}).get("lawsuits", [])

        if not processos:
            return {"message": "Nenhum processo encontrado."}

        empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()
        
        if not empresa:
            raise HTTPException(status_code=400, detail="Empresa não cadastrada")
        
        try:
            sintese_data = await get_empresa_sintese(db, empresa.id)
            sintese = sintese_data.get("texto")
        except Exception as e:
            print(f"Erro ao obter síntese: {str(e)}")
            sintese = "Informações da empresa indisponíveis"
            
        # TODO: a avaliação do processo não será tão boa sem os valores e/ou autos dos processos
        agent_input = f"""
            Você é um analista de risco jurídico especializado em processos judiciais, focado em avaliar o impacto dos litígios sobre a reputação, as finanças e a continuidade dos negócios da empresa {empresa.nome}. Além disso, considere a síntese atual da empresa: {sintese}, para melhor contextualizar sua análise.

            Sua tarefa é analisar cada processo judicial em andamento e atribuir, de forma integrada, uma pontuação de relevância e risco, justificando sua avaliação com base na natureza, nos possíveis desdobramentos e na influência que o litígio pode ter na empresa.

            Para cada processo judicial, retorne um JSON contendo os seguintes campos:
            - "numero": número do processo judicial.
            - "relevance": pontuação de 1 a 10 que representa o impacto do processo nos negócios da empresa.
            - "risc": pontuação de 1 a 10 que indica o risco do processo para a reputação, finanças ou continuidade da empresa.
            - "description": breve justificativa, explicando os fatores que influenciaram a pontuação atribuída.
            - "resumo": um resumo que contextualize o processo.
            - "data_distribuicao": data de distribuição do processo no formato dd-mm-yyyy.

            Critérios para avaliação:
            - Para relevance e risc:
                • 1 a 2: Impacto ou risco baixo ou nulo: a empresa não sofrerá consequências relevantes com o processo.
                • 3 a 5: Impacto ou risco médio: a empresa pode ter algum envolvimento ou sofrer consequências moderadas, sendo importante monitorar de perto.
                • 6 a 10: Impacto ou risco alto: o processo possui potencial real de afetar significativamente os negócios, podendo, em casos extremos, comprometer a continuidade da empresa (6: requer muito cuidado; 10: risco absurdo, capaz de fechar a empresa amanhã).

            Formato esperado (como string JSON):
            [
                {{
                    "numero": "1234567-00.2024.8.26.0000",
                    "relevance": 7,
                    "risc": 8,
                    "resumo" : "A empresa está enfrentando um processo trabalhista movido por um ex-colaborador, que alega demissão indevida e reivindica verbas rescisórias e horas extras não pagas. O caso apresenta riscos financeiros moderados a altos, com possibilidade de condenação relevante. Além disso, o processo pode gerar impactos negativos à reputação da empresa, especialmente em razão da sua atual situação de vulnerabilidade e exposição pública. A recomendação é acompanhar de perto o andamento e considerar estratégias de mitigação de danos, incluindo eventual acordo extrajudicial.",
                    "description": "Processo trabalhista com riscos financeiros e potenciais impactos na reputação, considerando a vulnerabilidade atual da empresa.",
                    "data_distribuicao": "21-03-2024"
                }}
            ]

            Retorne APENAS o array JSON convertido em string, sem explicações, comentários ou qualquer outro texto.
        """
        
        agent = Agent(name="ProcessAnalyzer", instructions=agent_input, model="gpt-4.1-mini")
        
        print ("Agent Input", agent_input)
        contador_processos_analisados = 0
        for proc in processos:
            try:
                numero = proc.get("cnj")
                valor = proc.get("value")
                classifications = proc.get("classifications", [])  # ← lista de objetos

                ultima_movimentacao = proc.get("last_update", None)

                # Vara (primeiro tribunal, se houver)
                courts = proc.get("courts")
                vara = courts[0].get("name") if isinstance(courts, list) and courts else None

                # Comarca
                comarca = proc.get("court_acronym")

                # Assunto (primeiro assunto, se houver)
                subjects = proc.get("subjects")
                assunto = subjects[0].get("name") if isinstance(subjects, list) and subjects else None

                # Data de distribuição
                data_dist = proc.get("distribution_date")

                # Verifica duplicação
                existe = db.query(Processo).filter(
                    Processo.numero == numero,
                    Processo.empresa_id == empresa.id
                ).first()

                if existe:
                    continue

                # Formata data
                try:
                    data_dist_date = datetime.strptime(data_dist, "%Y-%m-%dT%H:%M:%S.%fZ") if data_dist else None
                    data_formatada = data_dist_date.strftime("%d-%m-%Y") if data_dist_date else ""
                except Exception:
                    data_formatada = datetime.today().strftime("%d-%m-%Y")

                prompt_input = json.dumps([proc])

                # Limite de caracteres do gpt
                max_chars = 100_000
                if len(prompt_input) > max_chars:
                    prompt_input = prompt_input[:max_chars]

                print(proc)

                def parse_data(data: str):
                    try:
                        return datetime.fromisoformat(data.replace("Z", "")).date()
                    except Exception:
                        pass

                    try:
                        return datetime.strptime(data, "%d-%m-%Y").date()
                    except Exception:
                        pass

                    print(f"Formato de data inválido: {data}")
                    return None

                ultimo_andamento_tipo = None
                ultimo_andamento_content = None
                ultimo_andamento_data = None

                if ultima_movimentacao:
                    ultimo_andamento_tipo = ultima_movimentacao.get("step_type")
                    ultimo_andamento_content = ultima_movimentacao.get("content")
                    ultimo_andamento_data = ultima_movimentacao.get("step_date")

                if data_dist and esta_no_intervalo(data_dist, data_inicio_date, data_fim_date) and contador_processos_analisados < 30:
                    print("Analisando processo ")

                    result = await Runner.run(agent, input=prompt_input)
                    resultado = extrair_json_do_texto(result.final_output)

                    if not resultado:
                        continue

                    item = resultado[0]

                    contador_processos_analisados += 1

                    novo_processo = Processo(
                        numero=numero,
                        valor = valor,
                        vara=vara,
                        ultimo_andamento_tipo = int(ultimo_andamento_tipo) if ultimo_andamento_tipo and str(ultimo_andamento_tipo).isdigit() else None,
                        ultimo_andamento_content=ultimo_andamento_content,
                        ultimo_andamento_data=parse_data(ultimo_andamento_data),
                        comarca=comarca,
                        assunto=assunto,
                        data_distribuicao=parse_data(item["data_distribuicao"]),
                        empresa_id=empresa.id,
                        relevance=item["relevance"],
                        risc=item["risc"],
                        description=item["description"],
                        resumo=item["resumo"],
                    )
                else:
                    print("Processo adicionado sem analise ")

                    novo_processo = Processo(
                        numero=numero,
                        vara=vara,
                        valor=valor,
                        comarca=comarca,
                        ultimo_andamento_tipo=int(ultimo_andamento_tipo) if ultimo_andamento_tipo and str(ultimo_andamento_tipo).isdigit() else None,
                        ultimo_andamento_content=ultimo_andamento_content,
                        ultimo_andamento_data=parse_data(ultimo_andamento_data),
                        assunto=assunto,
                        data_distribuicao=parse_data(data_dist),
                        empresa_id=empresa.id,
                        relevance=-1,
                        risc=-1,
                        description="NÃO ANALISADO PELO AGENTE",
                        resumo="NÃO ANALISADO PELO AGENTE",
                    )

                db.add(novo_processo)
                db.flush()

                for item in classifications:
                    try:
                        code = int(item.get("code"))
                    except (ValueError, TypeError):
                        code = -1

                    classificacao = ClassificacaoProcesso(
                        name=item.get("name"),
                        code=code,
                        process_sphere=get_process_sphere(code),
                        processo_id=novo_processo.id
                    )
                    db.add(classificacao)

            except Exception as e:
                print(f"Erro ao processar o processo {proc.get('cnj')}: {e}")
                continue

        db.flush()
        db.commit()
        return {"message": "Processos analisados e salvos com sucesso"}

    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Erro ao acessar a API Jusfy: {e}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=500, detail=f"Erro na resposta da API Jusfy: {e.response.status_code}")


def extrair_json_do_texto(texto: str):
    try:
        match = re.search(r'\[.*\]', texto, re.DOTALL)
        if not match:
            print("Nenhum JSON encontrado.")
            return None
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        print("Erro ao decodificar o JSON:", e)
        return None


async def consultar_processos_db(db, cnpj: str, data_inicio: date, data_fim: date):
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()
    if not empresa:
        raise HTTPException(status_code=400, detail="Empresa não cadastrada")

    # Query base
    query = db.query(Processo).filter(Processo.empresa_id == empresa.id)

    # Filtros de data
    if data_inicio:
        query = query.filter(Processo.data_distribuicao >= data_inicio)
    if data_fim:
        query = query.filter(Processo.data_distribuicao <= data_fim)

    processos = query.order_by(Processo.data_distribuicao.desc()).all()

    # Índice de risco ponderado
    ponderada_query = db.query(
        func.sum(Processo.risc * Processo.relevance).label("soma_ponderada"),
        func.sum(Processo.relevance).label("soma_pesos")
    ).filter(Processo.empresa_id == empresa.id)

    if data_inicio:
        ponderada_query = ponderada_query.filter(Processo.data_distribuicao >= data_inicio)
    if data_fim:
        ponderada_query = ponderada_query.filter(Processo.data_distribuicao <= data_fim)

    resultado = ponderada_query.one()
    soma_ponderada = resultado.soma_ponderada or 0
    soma_pesos = resultado.soma_pesos or 1  # evita divisão por zero

    ind_risc_valor = soma_ponderada / soma_pesos

    return {
        "ind_risc": round(ind_risc_valor, 2),
        "processos": processos
    }


from datetime import date, timedelta
from sqlalchemy import select, func, not_

async def contar_processos_por_esfera_db(
    db,
    cnpj: str,
    process_sphere: str,
    data_inicio: date = None,
    data_fim: date = None
) -> dict:
    # Buscar a empresa pelo CNPJ
    result = db.execute(select(Empresa).where(Empresa.cnpj == cnpj))
    empresa = result.scalars().first()

    if not empresa:
        return {"quantidade": 0, "mensagem": "Empresa não encontrada"}

    # Query principal com agregações (usando data_inicio e data_fim)
    stmt = (
        select(
            func.count(Processo.id).label("quantidade"),
            func.avg(Processo.valor).label("valor_medio"),
            func.sum(Processo.valor).label("valor_total")
        )
        .join(Processo.classificacoes)
        .where(Processo.empresa_id == empresa.id)
        .where(ClassificacaoProcesso.process_sphere == process_sphere)
        .where(Processo.valor.isnot(None))
        .where(Processo.valor > 0)
        .where(not_(Processo.ultimo_andamento_tipo == 848))
    )

    if data_inicio:
        stmt = stmt.where(Processo.data_distribuicao >= data_inicio)
    if data_fim:
        stmt = stmt.where(Processo.data_distribuicao <= data_fim)

    result = db.execute(stmt)
    row = result.first()

    # 🗓 Definir período das últimas 4 semanas com base em data_fim ou hoje
    end_date = data_fim or date.today()
    start_date = end_date - timedelta(weeks=4)

    # Query para os dados semanais (fixo: últimas 4 semanas antes de data_fim ou hoje)
    stmt_semanal = (
        select(
            func.date_trunc('week', Processo.data_distribuicao).label("semana"),
            func.count(Processo.id).label("quantidade")
        )
        .join(Processo.classificacoes)
        .where(Processo.empresa_id == empresa.id)
        .where(ClassificacaoProcesso.process_sphere == process_sphere)
        .where(Processo.data_distribuicao >= start_date)
        .where(Processo.data_distribuicao <= end_date)
        .where(Processo.valor.isnot(None))
        .where(Processo.valor > 0)
        .where(not_(Processo.ultimo_andamento_tipo == 848))
        .group_by(func.date_trunc('week', Processo.data_distribuicao))
    )

    resultados = db.execute(stmt_semanal).all()
    quantidades_dict = {semana.date(): quantidade for semana, quantidade in resultados}

    # Gera as últimas 4 semanas manualmente
    processos_por_semana = []
    for i in range(4):
        semana_base = end_date - timedelta(weeks=3 - i)
        segunda_feira = semana_base - timedelta(days=semana_base.weekday())
        processos_por_semana.append({
            "semana": segunda_feira.strftime("%Y-%m-%d"),
            "quantidade": quantidades_dict.get(segunda_feira, 0)
        })

    return {
        "quantidade": row.quantidade or 0,
        "valor_medio": float(row.valor_medio) if row.valor_medio is not None else 0.0,
        "valor_total": float(row.valor_total) if row.valor_total is not None else 0.0,
        "processos_por_semana": processos_por_semana
    }


async def buscar_processos_transitados_em_julgado_db(
    db,
    cnpj: str,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None
):
    # Buscar empresa pelo CNPJ
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()
    if not empresa:
        return []  # Ou levante uma exceção, se preferir

    # Construir a query base com o ID da empresa
    stmt = select(Processo).where(
        and_(
            Processo.empresa_id == empresa.id,
            Processo.ultimo_andamento_tipo == 848
        )
    )

    # Adicionar filtros de data, se fornecidos
    if data_inicio:
        stmt = stmt.where(Processo.data_distribuicao >= data_inicio)
    if data_fim:
        stmt = stmt.where(Processo.data_distribuicao <= data_fim)

    # Executar a consulta
    result = db.execute(stmt)
    processos = result.scalars().all()

    return {
        "processos": processos
    }



##  SERÁ UTILIZADA PARA EMITIR OS AVISOS, NAO FINALIZEI PQ NAO SEI COMO VAO FICAR OS AVISOS
async def identificar_variacoes_processos(
    db,
    cnpj: str,
    process_sphere: str,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None
) -> dict:
    # Busca os dados da empresa
    dados = await contar_processos_por_esfera_db(db, cnpj, process_sphere, data_inicio, data_fim)

    variacao_detectada = False
    semanas_com_variacao = []
    semanas = dados.get("processos_por_semana", [])

    for i in range(1, len(semanas)):
        semana_atual = semanas[i]
        semana_anterior = semanas[i - 1]

        qtd_atual = semana_atual["quantidade"]
        qtd_anterior = semana_anterior["quantidade"]

        if qtd_anterior == 0:
            continue  # Ignora divisão por zero

        variacao = ((qtd_atual - qtd_anterior) / qtd_anterior) * 100

        if variacao > 20:
            variacao_detectada = True
            semanas_com_variacao.append({
                "de": semana_anterior["semana"],
                "para": semana_atual["semana"],
                "percentual": round(variacao, 2)
            })

    return {
        "quantidade": dados["quantidade"],
        "processos_por_semana": dados["processos_por_semana"],
        "variacao_detectada": variacao_detectada,
        "semanas_com_variacao": semanas_com_variacao
    }


async def verificar_e_criar_aviso_variacao_processos(
    db,
    cnpj: str,
    process_sphere: str
):
    # Buscar dinamicamente o módulo jurídico da empresa com base no CNPJ
    stmt_modulo = (
        select(Monitoramento)
        .join(Empresa, Monitoramento.empresa_id == Empresa.id)
        .where(
            func.lower(Monitoramento.modulo) == "juridico",
            Empresa.cnpj == cnpj
        )
    )
    result_modulo = db.execute(stmt_modulo)
    modulo_juridico = result_modulo.scalars().first()

    if not modulo_juridico:
        print("Módulo jurídico não encontrado.")
        return

    modulo_juridico_id = modulo_juridico.id

    # Executa a análise de variação
    variacoes = await identificar_variacoes_processos(db, cnpj, process_sphere)

    if not variacoes["variacao_detectada"]:
        print("Nenhuma variacao detectada para esfera " + process_sphere)
        return

    semanas_com_variacao = variacoes["semanas_com_variacao"]
    if not semanas_com_variacao:
        return

    ultima_variacao = semanas_com_variacao[-1]
    hoje = date.today()

    # Verifica se já existe aviso com a mesma classe hoje
    stmt = select(Aviso).where(
        and_(
            Aviso.classe_aviso == f"variacao_qtd_processos_{process_sphere}",
            Aviso.modulo_associado_id == modulo_juridico_id,
            func.date(Aviso.criado_em) == hoje
        )
    )
    resultado = db.execute(stmt)
    aviso_existente = resultado.scalars().first()

    if aviso_existente:
        return  # Já existe aviso criado hoje

    percentual = ultima_variacao["percentual"]

    # Classificação de importância com base no percentual
    if percentual < 20:
        nivel_importancia = 2
    elif percentual < 50:
        nivel_importancia = 5
    elif percentual < 80:
        nivel_importancia = 7
    else:
        nivel_importancia = 10

    mensagem = (
        f"Detectamos uma variação de {percentual}% na quantidade de processos da esfera {process_sphere} "
        f"dentro das últimas 4 semanas."
    )

    print(mensagem)

    novo_aviso = Aviso(
        mensagem=mensagem,
        nivel_importancia=nivel_importancia,
        classe_aviso=f"variacao_qtd_processos_{process_sphere}",
        criado_em=datetime.utcnow(),
        modulo_associado_id=modulo_juridico_id
    )

    db.add(novo_aviso)
    db.commit()

async def verificar_variacao_indice_risco_juridico(db, cnpj: str):
    # Buscar o módulo jurídico da empresa
    stmt_modulo = (
        select(Monitoramento)
        .join(Empresa, Monitoramento.empresa_id == Empresa.id)
        .where(
            func.lower(Monitoramento.modulo) == "juridico",
            Empresa.cnpj == cnpj
        )
    )
    result_modulo = db.execute(stmt_modulo)
    modulo_juridico = result_modulo.scalars().first()

    if not modulo_juridico:
        print("Módulo jurídico não encontrado.")
        return

    modulo_juridico_id = modulo_juridico.id
    hoje = date.today()

    # Verifica se já existe aviso emitido hoje
    aviso_existente = db.execute(
        select(Aviso).where(
            and_(
                Aviso.classe_aviso == "variacao_diaria_indice_risco_juridico",
                Aviso.modulo_associado_id == modulo_juridico_id,
                func.date(Aviso.criado_em) == hoje
            )
        )
    ).scalars().first()

    if aviso_existente:
        print("Aviso já criado hoje.")
        return

    def calcular_indice_risco_por_dia(data_alvo):
        resultado = db.query(
            func.sum(Processo.risc * Processo.relevance).label("soma_ponderada"),
            func.sum(Processo.relevance).label("soma_pesos")
        ).join(Empresa).filter(
            Empresa.cnpj == cnpj,
            Processo.data_distribuicao == data_alvo
        ).one()
        soma_ponderada = resultado.soma_ponderada or 0
        soma_pesos = resultado.soma_pesos or 1
        return round(soma_ponderada / soma_pesos, 2)

    # Coleta os índices dos últimos 3 dias
    indices = []
    for i in range(2, -1, -1):  # anteontem, ontem, hoje
        dia = hoje - timedelta(days=i)
        indice = calcular_indice_risco_por_dia(dia)
        indices.append((dia, indice))

    # Verifica variações positivas maiores que 20%
    variacoes_relevantes = []
    for i in range(1, len(indices)):
        dia_ant, ind_ant = indices[i - 1]
        dia_atual, ind_atual = indices[i]

        if ind_ant == 0:
            continue  # evitar divisão por zero

        variacao = ((ind_atual - ind_ant) / ind_ant) * 100
        if variacao > 20:
            variacoes_relevantes.append({
                "de": dia_ant.strftime("%d/%m/%Y"),
                "para": dia_atual.strftime("%d/%m/%Y"),
                "variacao": round(variacao, 2)
            })

    if not variacoes_relevantes:
        print("Nenhuma variação de aumento de risco (>20%) nos últimos 3 dias. - juridico")
        return

    maior_variacao = max(v["variacao"] for v in variacoes_relevantes)
    if maior_variacao < 30:
        nivel_importancia = 5
    elif maior_variacao < 50:
        nivel_importancia = 7
    else:
        nivel_importancia = 10

    # Monta mensagem
    partes = [
        f"aumentou {v['variacao']}% entre os dias {v['de']} e {v['para']}"
        for v in variacoes_relevantes
    ]
    mensagem = "O índice de risco jurídico " + ", e ".join(partes) + "."

    print(mensagem)

    novo_aviso = Aviso(
        mensagem=mensagem,
        nivel_importancia=nivel_importancia,
        classe_aviso="variacao_diaria_indice_risco_juridico",
        criado_em=datetime.utcnow(),
        modulo_associado_id=modulo_juridico_id
    )

    db.add(novo_aviso)
    db.commit()


def consultar_indice_risco_db(db, cnpj: str, data_inicio: date, data_fim: date):
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()
    if not empresa:
        raise HTTPException(status_code=400, detail="Empresa não cadastrada")

    query = db.query(
        func.sum(Processo.risc * Processo.relevance).label("soma_ponderada"),
        func.sum(Processo.relevance).label("soma_pesos")
    ).filter(Processo.empresa_id == empresa.id)

    if data_inicio:
        query = query.filter(Processo.data_distribuicao >= data_inicio)
    if data_fim:
        query = query.filter(Processo.data_distribuicao <= data_fim)

    resultado = query.one()
    soma_ponderada = resultado.soma_ponderada or 0
    soma_pesos = resultado.soma_pesos or 1  # evita divisão por zero

    ind_risc_valor = soma_ponderada / soma_pesos

    return {"indice_risco": round(ind_risc_valor, 2)}