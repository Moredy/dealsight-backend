from agents import Agent, Runner  # Supondo que você já tenha essas classes
import json
import re
import httpx
from httpx import HTTPStatusError, RequestError, TimeoutException
from fastapi import HTTPException

from model.models import Sintese
from service.sinteses import get_empresa_sintese

from datetime import date, datetime, timedelta
from sqlalchemy import select, and_, func
from model.models import Empresa, Monitoramento, Aviso, DividaAtivaUniao  # ajuste conforme necessário


API_BACKEND_SCRAPPING = 'http://45.32.221.63:5000'


def extrair_json_do_texto(texto: str):
    try:
        match = re.search(r'\{.*\}', texto, re.DOTALL)
        if not match:
            print("Nenhum JSON encontrado no texto.")
            return None
        json_str = match.group(0)
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print("Erro ao decodificar o JSON:", e)
        return None




async def analisar_divida_uniao_com_agente(valor_total: float,empresa, db) -> dict:

    # Get the latest summary using our new system
    try:
        sintese_data = await get_empresa_sintese(db, empresa.id)
        sintese = sintese_data["texto"]
    except Exception as e:
        print(f"Erro ao obter síntese: {str(e)}")
        sintese = "Informações da empresa indisponíveis."

    agent = Agent(
        name="CreditUnionAnalyst",
        instructions=f"""
        Você é um analista financeiro. Sua tarefa é avaliar o risco e a relevância de cada dívida ativa da ${empresa.nome}.Além disso, considere a síntese atual da empresa: {sintese}, para melhor contextualizar sua análise.
        Considere o porte da empresa e histórico da empresa e a solitude da empresa, caso a divida não for ter um impacto consideravel nos proximos dias, diminua o risco e relevancia


        Retorne um JSON com os seguintes campos:
        {{
          "risco": float entre 0 e 10 (quanto maior, mais arriscado),
          "relevancia": float entre 0 e 10 (quanto maior, mais relevante),
          "descricao": string explicando os critérios
        }}

        Exemplo:
        {{
          "risco": 4,
          "relevancia": 5,
          "descricao": "Valor alto da dívida pode impactar significativamente uma empresa de médio porte."
        }}

        Apenas retorne o JSON como string. Não adicione comentários ou explicações fora dele.
        """
    )

    prompt = json.dumps({
        "valor_total": valor_total
    })

    result = await Runner.run(agent, input=prompt)
    return extrair_json_do_texto(result.final_output)


async def buscar_salvar_divida_ativa_uniao_db(db, cnpj: str):
    def limpar_cnpj(cnpj: str) -> str:
        return re.sub(r'\D', '', cnpj)

    body = {
        "cnpj": limpar_cnpj(cnpj),
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_BACKEND_SCRAPPING}/pesquisar",
                json=body,
                timeout=60
            )
            response.raise_for_status()
            divida_data = response.json()

            if not divida_data:
                raise HTTPException(status_code=500, detail="Erro ao consultar dívida ativa")

            empresa = db.query(Empresa).filter(Empresa.cnpj == limpar_cnpj(cnpj)).first()

            analise_existente = db.query(DividaAtivaUniao).filter(
                DividaAtivaUniao.empresa_id == empresa.id,
                func.date(DividaAtivaUniao.data_consulta) == date.today()
            ).first()

            if analise_existente:
                print("Já existe uma análise para hoje. Ignorando gravação.")
                return {"message": "Dívida encontrada já na base"}

            if not empresa:
                raise HTTPException(status_code=400, detail="Empresa não cadastrada")

            try:
                total_divida = float(divida_data["devedores"][0]["totaldivida"])
            except (KeyError, IndexError, TypeError, ValueError):
                total_divida = 0

            # Análise com o agente
            analise = await analisar_divida_uniao_com_agente(total_divida, empresa, db)
            if not analise:
                raise HTTPException(status_code=500, detail="Erro ao analisar a dívida com IA")

            nova_divida = DividaAtivaUniao(
                empresa_id=empresa.id,
                total_divida=total_divida,
                risco=analise["risco"],
                relevancia=analise["relevancia"],
                descricao=analise["descricao"],
                data_consulta=datetime.utcnow()
            )

            db.add(nova_divida)
            db.commit()

            return {"message": "Dívida ativa analisada e salva com sucesso"}

    except HTTPStatusError as exc:
        print(f"Erro HTTP ao acessar {exc.request.url!r} - Status: {exc.response.status_code}")
    except TimeoutException:
        print("A requisição excedeu o tempo limite.")
    except RequestError as exc:
        print(f"Erro de requisição ao tentar acessar {exc.request.url!r}: {exc}")
    except Exception as exc:
        print(f"Ocorreu um erro inesperado: {exc}")


def consultar_divida_uniao_db(db, cnpj: str):

    def limpar_cnpj(cnpj: str) -> str:
        return re.sub(r'\D', '', cnpj)

    cnpj = limpar_cnpj(cnpj)

    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()
    if not empresa:
        raise HTTPException(status_code=400, detail="Empresa não cadastrada")

    dividas = (
        db.query(DividaAtivaUniao)
        .filter(DividaAtivaUniao.empresa_id == empresa.id)
        .order_by(DividaAtivaUniao.data_consulta.desc())
        .all()
    )

    if not dividas:
        return {
            "divida_mais_recente": None,
            "soma_total": 0,
            "risco_medio_ponderado": 0,
            "data_consulta_recente": None
        }

    # Dívida mais recente
    divida_mais_recente = dividas[0]

    # Soma total (se houver mais de uma)
    soma_total = sum(d.total_divida or 0 for d in dividas)

    # Risco médio ponderado
    soma_ponderada = sum((d.risco or 0) * (d.relevancia or 0) for d in dividas)
    soma_pesos = sum(d.relevancia or 0 for d in dividas) or 1  # evitar divisão por zero
    risco_medio_ponderado = soma_ponderada / soma_pesos

    return {
        "divida_mais_recente": {
            "total_divida": round(divida_mais_recente.total_divida, 2),
            "risco": round(divida_mais_recente.risco, 2),
            "relevancia": round(divida_mais_recente.relevancia, 2),
            "descricao": divida_mais_recente.descricao,
            "data_consulta": divida_mais_recente.data_consulta
        },
        "soma_total": round(soma_total, 2),
        "risco_medio_ponderado": round(risco_medio_ponderado, 2),
        "data_consulta_recente": divida_mais_recente.data_consulta
    }


async def verificar_e_criar_aviso_divida_ativa_uniao(db, cnpj: str):
    # Buscar módulo de dívida ativa União
    stmt_modulo = (
        select(Monitoramento)
        .join(Empresa, Monitoramento.empresa_id == Empresa.id)
        .where(
            func.lower(Monitoramento.modulo) == "divida-ativa-uniao",
            Empresa.cnpj == cnpj
        )
    )
    result_modulo = db.execute(stmt_modulo)
    modulo_divida = result_modulo.scalars().first()

    if not modulo_divida:
        print("Módulo de dívida ativa União não encontrado.")
        return

    modulo_divida_id = modulo_divida.id
    hoje = date.today()

    # Verifica se já existe aviso criado hoje
    aviso_existente = db.execute(
        select(Aviso).where(
            and_(
                Aviso.classe_aviso == "variacao_diaria_indice_risco_divida_ativa_uniao",
                Aviso.modulo_associado_id == modulo_divida_id,
                func.date(Aviso.criado_em) == hoje
            )
        )
    ).scalars().first()

    if aviso_existente:
        print("Aviso de variação diária no índice de risco de dívida ativa União já criado hoje.")
        return

    def calcular_indice_risco_para_data(data_alvo):
        resultado = db.query(
            func.sum(DividaAtivaUniao.risco * DividaAtivaUniao.relevancia).label("soma_ponderada"),
            func.sum(DividaAtivaUniao.relevancia).label("soma_pesos")
        ).select_from(DividaAtivaUniao).join(Empresa, Empresa.id == DividaAtivaUniao.empresa_id).filter(
            Empresa.cnpj == cnpj,
            DividaAtivaUniao.data_consulta == data_alvo
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
        print("Nenhuma variação de aumento de risco (>20%) nos últimos 3 dias. - divida-ativa-uniao")
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

    mensagem = "O índice de risco da dívida ativa federal " + ", e ".join(partes_mensagem) + "."

    print(mensagem)

    novo_aviso = Aviso(
        mensagem=mensagem,
        nivel_importancia=nivel_importancia,
        classe_aviso="variacao_diaria_indice_risco_divida_ativa_uniao",
        criado_em=datetime.utcnow(),
        modulo_associado_id=modulo_divida_id
    )

    db.add(novo_aviso)
    db.commit()