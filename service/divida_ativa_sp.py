from agents import Agent, Runner  # Supondo que você já tenha essas classes
import json
import re
import httpx
from fastapi import HTTPException

from model.models import Sintese
from service.sinteses import get_empresa_sintese

from datetime import date, datetime, timedelta
from sqlalchemy import select, and_, func
from model.models import Empresa, Monitoramento, Aviso, DividaAtivaSp  # ajuste os imports conforme sua estrutura


API_BACKEND_SCRAPPING = 'http://45.32.221.63:5000'


def extrair_json_do_texto(texto: str):
    try:
        match = re.search(r'\[.*\]', texto, re.DOTALL)
        if not match:
            print("Nenhum JSON encontrado no texto.")
            return None

        json_str = match.group(0)
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print("Erro ao decodificar o JSON:", e)
        return None

async def analisar_dividas_com_agente(divida: list, empresa,db):

    # Get the latest summary using our new system
    try:
        sintese_data = await get_empresa_sintese(db, empresa.id)
        sintese = sintese_data["texto"]
    except Exception as e:
        print(f"Erro ao obter síntese: {str(e)}")
        sintese = "Informações da empresa indisponíveis."

    agent = Agent(
        name="CreditRiskBot",
        instructions=f"""
        Você é um analista financeiro. Sua tarefa é avaliar o risco e a relevância de cada dívida ativa da ${empresa.nome}.Além disso, considere a síntese atual da empresa: {sintese}, para melhor contextualizar sua análise.
        Considere o porte da empresa e histórico da empresa e a solitude da empresa, caso a divida não for ter um impacto consideravel nos proximos dias, diminua o risco e relevancia

        Para cada dívida, retorne um JSON com:
        - origem
        - tipo
        - quantidade
        - valor_total
        - risco: float entre 0 e 10 (quanto maior, mais arriscado)
        - relevancia: float entre 0 e 10 (quanto maior, mais relevante)
        - descricao: uma breve explicação da avaliação

        Exemplo de saída (como string JSON):
        [
          {{
            "origem": "Procuradoria",
            "tipo": "ICMS",
            "quantidade": 5,
            "valor_total": "35000.00",
            "risco": 4,
            "relevancia": 5,
            "descricao": "Dívida com valor relevante e frequência alta, indica risco moderado."
          }}
        ]

        Apenas responda com o JSON como string, sem explicações adicionais.
        """
    )


    prompt = json.dumps([divida])
    result = await Runner.run(agent, input=prompt)
    resultado_formatado = extrair_json_do_texto(result.final_output)


    return resultado_formatado

async def buscar_salvar_divida_ativa_sp_db(db, cnpj: str):
    body = {
        "cnpj": re.sub(r'\D', '', cnpj),
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_BACKEND_SCRAPPING}/divida-ativa-sp",
                json=body,
                timeout=60
            )
            response.raise_for_status()
            divida_data = response.json()

            if not divida_data:
                raise HTTPException(status_code=500, detail="Erro ao consultar dívida ativa")

            empresa = db.query(Empresa).filter(Empresa.cnpj == body["cnpj"]).first()
            if not empresa:
                raise HTTPException(status_code=400, detail="Empresa não cadastrada")

            # Verifica se já existe uma análise com a data de hoje para esse CNPJ
            analise_existente = db.query(DividaAtivaSp).filter(
                DividaAtivaSp.empresa_id == empresa.id,
                func.date(DividaAtivaSp.data_consulta) == date.today()
            ).first()

            if analise_existente:
                print("Já existe uma análise para hoje. Ignorando gravação.")
                return {"message": "Dívida encontrada já na base"}

            if isinstance(divida_data, dict) and divida_data.get('message') == 'Nenhum resultado encontrado':
                nova_divida = DividaAtivaSp(
                    origem='-',
                    quantidade=0,
                    tipo='-',
                    total_divida=0,
                    empresa_id=empresa.id,
                    risco=0,
                    relevancia=0,
                    descricao='Não existe dívida.'
                )
                db.add(nova_divida)
            else:
                for divida in divida_data:
                    analise = await analisar_dividas_com_agente(divida, empresa,db)

                    nova_divida = DividaAtivaSp(
                        origem=divida["origem"],
                        quantidade=int(divida["quantidade"]),
                        tipo=divida["tipo"],
                        total_divida=float(divida["valor_total"].replace('.', '').replace(',', '.')),
                        empresa_id=empresa.id,
                        risco=analise[0]['risco'],
                        relevancia=analise[0]['relevancia'],
                        descricao=analise[0]['descricao']
                    )
                    db.add(nova_divida)

            db.commit()

            return {"message": "Dívida ativa analisada e salva com sucesso"}

    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Erro na requisição: {str(e)}")


def consultar_divida_sp_db(db, cnpj: str):

    def limpar_cnpj(cnpj: str) -> str:
        return re.sub(r'\D', '', cnpj)

    cnpj = limpar_cnpj(cnpj)

    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()
    if not empresa:
        raise HTTPException(status_code=400, detail="Empresa não cadastrada")

    dividas = (
        db.query(DividaAtivaSp)
        .filter(DividaAtivaSp.empresa_id == empresa.id)
        .order_by(DividaAtivaSp.data_consulta.desc())
        .all()
    )

    if not dividas:
        return {
            "dividas_filtradas": [],
            "soma_total": 0,
            "risco_medio_ponderado": 0,
            "data_consulta_recente": None
        }

    # Filtrar para manter apenas a dívida mais recente de cada tipo
    tipos_unicos = {}
    for divida in dividas:
        if divida.tipo not in tipos_unicos:
            tipos_unicos[divida.tipo] = divida

    dividas_filtradas = list(tipos_unicos.values())

    # Calcular soma total da dívida
    soma_total = sum(d.total_divida or 0 for d in dividas_filtradas)

    # Calcular risco médio ponderado (usando relevância como peso)
    soma_ponderada = sum((d.risco or 0) * (d.relevancia or 0) for d in dividas_filtradas)
    soma_pesos = sum(d.relevancia or 0 for d in dividas_filtradas) or 1  # evita divisão por zero
    risco_medio_ponderado = soma_ponderada / soma_pesos

    # Pegar data da consulta mais recente (da primeira dívida da lista original ordenada)
    data_consulta_recente = dividas[0].data_consulta if dividas else None

    return {
        "dividas_filtradas": dividas_filtradas,
        "soma_total": round(soma_total, 2),
        "risco_medio_ponderado": round(risco_medio_ponderado, 2),
        "data_consulta_recente": data_consulta_recente,
    }


async def verificar_e_criar_aviso_divida_ativa_sp(db, cnpj: str):
    # Buscar módulo de dívida ativa SP
    stmt_modulo = (
        select(Monitoramento)
        .join(Empresa, Monitoramento.empresa_id == Empresa.id)
        .where(
            func.lower(Monitoramento.modulo) == "divida-ativa-sp",
            Empresa.cnpj == cnpj
        )
    )
    result_modulo = db.execute(stmt_modulo)
    modulo_divida = result_modulo.scalars().first()

    if not modulo_divida:
        print("Módulo de dívida ativa SP não encontrado.")
        return

    modulo_divida_id = modulo_divida.id
    hoje = date.today()

    # Verifica se já existe aviso criado hoje
    aviso_existente = db.execute(
        select(Aviso).where(
            and_(
                Aviso.classe_aviso == "variacao_diaria_indice_risco_divida_ativa_sp",
                Aviso.modulo_associado_id == modulo_divida_id,
                func.date(Aviso.criado_em) == hoje
            )
        )
    ).scalars().first()

    if aviso_existente:
        print("Aviso de variação diária no índice de risco de dívida ativa SP já criado hoje.")
        return

    def calcular_indice_risco_para_data(data_alvo):
        resultado = db.query(
            func.sum(DividaAtivaSp.risco * DividaAtivaSp.relevancia).label("soma_ponderada"),
            func.sum(DividaAtivaSp.relevancia).label("soma_pesos")
        ).select_from(DividaAtivaSp).join(Empresa, Empresa.id == DividaAtivaSp.empresa_id).filter(
            Empresa.cnpj == cnpj,
            DividaAtivaSp.data_consulta == data_alvo
        ).one()

        soma_ponderada = resultado.soma_ponderada or 0
        soma_pesos = resultado.soma_pesos or 1
        return round(soma_ponderada / soma_pesos, 2)

    # Coleta os índices dos últimos 3 dias
    indices = []
    for i in range(2, -1, -1):  # anteontem, ontem, hoje
        dia = hoje - timedelta(days=i)
        indice = calcular_indice_risco_para_data(dia)
        indices.append((dia, indice))

    variacoes_relevantes = []

    for i in range(1, len(indices)):
        dia_anterior, indice_anterior = indices[i - 1]
        dia_atual, indice_atual = indices[i]

        if indice_anterior == 0:
            continue  # evita divisão por zero

        variacao = ((indice_atual - indice_anterior) / indice_anterior) * 100
        variacao = round(variacao, 2)

        if variacao > 20:  # só considera aumento de risco
            variacoes_relevantes.append({
                "de": dia_anterior.strftime('%d/%m/%Y'),
                "para": dia_atual.strftime('%d/%m/%Y'),
                "variacao": variacao
            })

    if not variacoes_relevantes:
        print("Nenhuma variação de aumento de risco (>20%) nos últimos 3 dias - divida-ativa-sp.")
        return

    # Define importância com base no maior aumento
    maior_variacao = max(v["variacao"] for v in variacoes_relevantes)
    if maior_variacao < 30:
        nivel_importancia = 5
    elif maior_variacao < 50:
        nivel_importancia = 7
    else:
        nivel_importancia = 10

    partes_mensagem = [
        f"aumentou {v['variacao']}% entre os dias {v['de']} e {v['para']}"
        for v in variacoes_relevantes
    ]

    mensagem = "O índice de risco da dívida ativa estadual " + ", e ".join(partes_mensagem) + "."

    print(mensagem)

    novo_aviso = Aviso(
        mensagem=mensagem,
        nivel_importancia=nivel_importancia,
        classe_aviso="variacao_diaria_indice_risco_divida_ativa_sp",
        criado_em=datetime.utcnow(),
        modulo_associado_id=modulo_divida_id
    )

    db.add(novo_aviso)
    db.commit()