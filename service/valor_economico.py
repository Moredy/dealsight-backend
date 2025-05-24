from agents import Agent, Runner  # Supondo que você já tenha essas classes
import json
import re
import httpx
from httpx import HTTPStatusError, RequestError, TimeoutException
from fastapi import HTTPException


from datetime import date, datetime, timedelta
from sqlalchemy import select, and_, func
from model.models import Empresa, Monitoramento, Aviso, NoticiaValorEconomico  # ajuste conforme necessário

API_BACKEND_SCRAPPING = 'http://45.32.221.63:5000'

# REGEX para casos com "Empresa:"
REGEX_EMPRESA = re.compile(
    r"Empresa:\s*(?P<empresa>.*?)(?:,\s*Nome Fantasia\s*.*?|)\s*-\s*"
    r"CNPJ:\s*(?P<cnpj>\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\s*-\s*"
    r"Endereço:\s*(?P<endereco>.*?)(?:\s*-\s*Administrador Judicial:\s*(?P<administrador_judicial>.*?))?"
    r"\s*-\s*Vara/Comarca:\s*(?P<vara_comarca>.*?)(?:\s*-\s*Observação:\s*(?P<observacao>.*))?$",
    re.IGNORECASE
)

# REGEX para casos com "Requerido:"
REGEX_REQUERIDO = re.compile(
    r"Requerido:\s*(?P<requerido>.*?)\s*-\s*"
    r"(?:CNPJ:\s*(?P<cnpj>\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\s*-\s*)?"
    r"(?:Endereço:\s*(?P<endereco>.*?)\s*-\s*)?"  # Endereço agora é opcional
    r"Requerente:\s*(?P<requerente>.*?)\s*-\s*"
    r"Vara/Comarca:\s*(?P<vara_comarca>.*?)(?:\s*-\s*Observação:\s*(?P<observacao>.*))?$",
    re.IGNORECASE
)

def extrair_dados(texto: str):
    if m := REGEX_EMPRESA.search(texto):
        return {**m.groupdict(), "tipo": "empresa"}
    if m := REGEX_REQUERIDO.search(texto):
        return {**m.groupdict(), "tipo": "requerido"}
    return None


async def analisar_valor_economico_com_agente(titulo, texto, cnpj):
    agent = Agent(
        name="ValorEconBot",
        instructions=f"""
        Considere o porte da empresa e histórico da empresa e a solitude da empresa, caso a divida não for ter um impacto consideravel nos proximos dias, diminua o risco e relevancia
        Você é um analista de risco. Avalie o conteúdo de uma notícia do jornal Valor Econômico a respeito da empresa com cnpj {cnpj} e indique:


        - risco: float entre 0 e 10 (quanto maior, maior o risco para a empresa)
        - relevancia: float entre 0 e 10 (quanto maior, mais relevante é a notícia)
        - descricao: uma explicação breve

        Retorne apenas o JSON no formato:
        {{
          "risco": 7,
          "relevancia": 8,
          "descricao": "Notícia relacionada a recuperação judicial, impacto alto."
        }}

        Nenhum texto fora do JSON.
        """
    )

    prompt = json.dumps({
        "titulo": titulo,
        "conteudo": texto
    })

    result = await Runner.run(agent, input=prompt)
    try:
        json_str = re.search(r'\{.*\}', result.final_output, re.DOTALL).group(0)
        return json.loads(json_str)
    except Exception as e:
        print("Erro ao extrair JSON da IA:", e)
        return {"risco": 0.5, "relevancia": 0.5, "justificativa": "Análise padrão (fallback)"}

# Função principal
async def buscar_salvar_dados_valor_economico_db(db):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_BACKEND_SCRAPPING}/valor-economico",
                timeout=60
            )
            response.raise_for_status()
            valor_economico_data = response.json()

            if not valor_economico_data:
                raise HTTPException(status_code=500, detail="Erro ao consultar valor econômico")

            data_publicacao = valor_economico_data.get("data_publicacao")

            for titulo, paragrafos in valor_economico_data["conteudo"].items():
                for texto in paragrafos:
                    dados = extrair_dados(texto)
                    if not dados:
                        continue  # pula se não deu match com nenhum regex

                    # Campos padrão
                    cnpj = dados.get("cnpj")
                    cnpj = ''.join(filter(str.isdigit, cnpj)) if cnpj else None  # ✅ limpar CNPJ

                    empresa = dados.get("empresa") or dados.get("requerido")
                    endereco = dados.get("endereco")
                    administrador_judicial = dados.get("administrador_judicial") or dados.get("requerente")
                    vara_comarca = dados.get("vara_comarca")
                    observacao = dados.get("observacao")

                    # ⚠️ Verifica se já existe
                    ja_existe = db.query(NoticiaValorEconomico).filter(
                        and_(
                            NoticiaValorEconomico.titulo == titulo,
                            NoticiaValorEconomico.cnpj == cnpj,
                            NoticiaValorEconomico.data_publicacao == data_publicacao,
                        )
                    ).first()

                    if ja_existe:
                        continue



                    analise = await analisar_valor_economico_com_agente(titulo, texto, cnpj)

                    nova = NoticiaValorEconomico(
                        titulo=titulo,
                        empresa=empresa,
                        cnpj=cnpj,
                        endereco=endereco,
                        administrador_judicial=administrador_judicial,
                        vara_comarca=vara_comarca,
                        observacao=observacao,
                        data_publicacao=data_publicacao,
                        risco=analise["risco"],
                        relevancia=analise["relevancia"],
                        descricao=analise["descricao"]
                    )

                    db.add(nova)
                    db.flush()  # garante verificação antes de salvar em lote

            db.commit()
            return {"message": "Dados do Valor Econômico analisados e salvos com sucesso"}

    except HTTPStatusError as exc:
        print(f"Erro HTTP ao acessar {exc.request.url!r} - Status: {exc.response.status_code}")
    except TimeoutException:
        print("A requisição excedeu o tempo limite.")
    except RequestError as exc:
        print(f"Erro de requisição ao tentar acessar {exc.request.url!r}: {exc}")
    except Exception as exc:
        print(f"Ocorreu um erro inesperado: {exc}")


async def consultar_noticias_valor_economico_cnpj_db(db, cnpj: str):
    def limpar_cnpj(cnpj: str) -> str:
        return re.sub(r'\D', '', cnpj)

    cnpj = limpar_cnpj(cnpj)

    noticias = db.query(NoticiaValorEconomico).filter(
        NoticiaValorEconomico.cnpj == cnpj
    ).order_by(NoticiaValorEconomico.data_publicacao.desc()).all()

    if not noticias:
        return {
            "noticias": [],
            "risco_medio_ponderado": 0
        }

    for noticia in noticias:
        if noticia.relevancia == -1 and noticia.risco -1 and noticia.descricao == 'NÃO ANALISADO PELO AGENTE':
            noticia_analisada = await analisar_valor_economico_com_agente(noticia.titulo, noticia.titulo + " "+ noticia.empresa, cnpj)
            noticia.relevancia = noticia_analisada.get("relevancia", -1)
            noticia.risco = noticia_analisada.get("risco", -1)
            noticia.descricao = noticia_analisada.get("descricao", "NÃO ANALISADO PELO AGENTE")

            db.commit()

    soma_ponderada = sum((n.risco or 0) * (n.relevancia or 0) for n in noticias)
    soma_pesos = sum(n.relevancia or 0 for n in noticias) or 1
    risco_medio_ponderado = soma_ponderada / soma_pesos

    return {
        "noticias": noticias,
        "risco_medio_ponderado": round(risco_medio_ponderado, 2)
    }

async def consultar_risco_valor_economico_db(db, cnpj: str):
    import re

    def limpar_cnpj(cnpj: str) -> str:
        return re.sub(r'\D', '', cnpj)

    cnpj = limpar_cnpj(cnpj)

    noticias = db.query(NoticiaValorEconomico).filter(
        NoticiaValorEconomico.cnpj == cnpj
    ).order_by(NoticiaValorEconomico.data_publicacao.desc()).all()

    for noticia in noticias:
        if (
            noticia.relevancia == -1 and
            noticia.risco == -1 and
            noticia.descricao == 'NÃO ANALISADO PELO AGENTE'
        ):
            noticia_analisada = await analisar_valor_economico_com_agente(
                noticia.titulo,
                f"{noticia.titulo} {noticia.empresa}",
                cnpj
            )
            noticia.relevancia = noticia_analisada.get("relevancia", -1)
            noticia.risco = noticia_analisada.get("risco", -1)
            noticia.descricao = noticia_analisada.get("descricao", "NÃO ANALISADO PELO AGENTE")
            db.commit()

    soma_ponderada = sum((n.risco or 0) * (n.relevancia or 0) for n in noticias)
    soma_pesos = sum(n.relevancia or 0 for n in noticias) or 1
    risco_medio_ponderado = soma_ponderada / soma_pesos

    return {"indice_risco": round(risco_medio_ponderado, 2)}


async def verificar_e_criar_aviso_movimentacoes_falimentares(db, cnpj: str):
    # Buscar módulo de movimentações falimentares
    stmt_modulo = (
        select(Monitoramento)
        .join(Empresa, Monitoramento.empresa_id == Empresa.id)
        .where(
            func.lower(Monitoramento.modulo) == "movimentacoes-falimentares",
            Empresa.cnpj == cnpj
        )
    )
    result_modulo = db.execute(stmt_modulo)
    modulo_falimentar = result_modulo.scalars().first()

    if not modulo_falimentar:
        print("Módulo de movimentações falimentares não encontrado.")
        return

    modulo_falimentar_id = modulo_falimentar.id
    hoje = date.today()

    # Verifica se já existe aviso criado hoje
    aviso_existente = db.execute(
        select(Aviso).where(
            and_(
                Aviso.classe_aviso == "variacao_diaria_indice_risco_movimentacoes_falimentares",
                Aviso.modulo_associado_id == modulo_falimentar_id,
                func.date(Aviso.criado_em) == hoje
            )
        )
    ).scalars().first()

    if aviso_existente:
        print("Aviso de variação diária no índice de risco de movimentações falimentares já criado hoje.")
        return

    def calcular_indice_risco_para_data(data_alvo):
        # Formata data alvo como string para comparar com o início do ISO (YYYY-MM-DD)
        data_str = data_alvo.strftime("%Y-%m-%d")

        resultado = db.query(
            func.sum(NoticiaValorEconomico.risco * NoticiaValorEconomico.relevancia).label("soma_ponderada"),
            func.sum(NoticiaValorEconomico.relevancia).label("soma_pesos")
        ).select_from(NoticiaValorEconomico).join(Empresa, Empresa.cnpj == NoticiaValorEconomico.cnpj).filter(
            Empresa.cnpj == cnpj,
            func.substr(NoticiaValorEconomico.data_publicacao, 1, 10) == data_str  # compara só a parte da data
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
        print("Nenhuma variação de aumento de risco (>20%) nos últimos 3 dias. - movimentacoes-falimentares")
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

    mensagem = "O índice de risco de movimentações falimentares " + ", e ".join(partes_mensagem) + "."

    print(mensagem)

    novo_aviso = Aviso(
        mensagem=mensagem,
        nivel_importancia=nivel_importancia,
        classe_aviso="variacao_diaria_indice_risco_movimentacoes_falimentares",
        criado_em=datetime.utcnow(),
        modulo_associado_id=modulo_falimentar_id
    )

    db.add(novo_aviso)
    db.commit()