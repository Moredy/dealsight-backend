
from fastapi import HTTPException, Request
import httpx
from schemas.noticias import NewsScrapperSchema, GetNewsSchema, PalavraChaveCreateSchema
from model.models import Empresa, Noticia, PalavraChave, Monitoramento, Sintese, Aviso
from datetime import date, timedelta
from pygooglenews import GoogleNews
from agents import Agent, Runner
import json
import re
from typing import List
import time
from datetime import datetime, date
from sqlalchemy import func, select, and_
import requests
from googlenewsdecoder import gnewsdecoder
import functools
from bs4 import BeautifulSoup

API_CNPJ_URL = "https://open.cnpja.com/office"

async def buscar_noticias_db(db, data: NewsScrapperSchema):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    def buscar_noticias_empresa(palavras_chave: List[str], data):
        gn = GoogleNews(country='BR', lang='pt-BR')
        hoje = date.today()

        data_inicio = (
            data.data_inicio.strftime('%Y-%m-%d')
            if data.data_inicio else (hoje - timedelta(days=1)).strftime('%Y-%m-%d')
        )

        data_fim = (
            data.data_fim.strftime('%Y-%m-%d')
            if data.data_fim else (hoje + timedelta(days=1)).strftime('%Y-%m-%d')
        )

        todas_noticias = []
        titulos_vistos = set()

        def extrair_link_real(google_news_url: str) -> str:
            decoded_url = gnewsdecoder(google_news_url)
            return decoded_url["decoded_url"]

        empresa = db.query(Empresa).filter(Empresa.cnpj == data.cnpj).first()

        for palavra in palavras_chave:

            #Adiciona contexto a busca
            if empresa.nome in palavra:
                palavra_com_contexto = palavra
            else:
                palavra_com_contexto = palavra + " " + empresa.nome

            print('Palavra chave : ' + palavra_com_contexto)
            search_result = gn.search(palavra_com_contexto, from_=data_inicio, to_=data_fim)
            entries = search_result.get('entries', [])

            for item in entries:
                titulo = item['title']
                link_google = item['link']
                published = time.strftime("%d-%m-%Y", item['published_parsed'])

                if len(todas_noticias) < data.limite_noticias:
                    if titulo not in titulos_vistos:

                        titulos_vistos.add(titulo)

                        link_real = extrair_link_real(link_google)

                        news_data = ''
                        try:
                            response_news_scrapping = requests.get(link_real, headers=headers, timeout=10)
                            soup = BeautifulSoup(response_news_scrapping.content, 'html.parser')

                            meta_desc = soup.find("meta", attrs={"name": "description"})
                            if meta_desc and meta_desc.get("content"):
                                news_data = meta_desc["content"]
                            else:
                                first_p = soup.find("p")
                                if first_p and len(first_p.text.strip()) > 30:
                                    news_data = first_p.text.strip()

                        except Exception as e:
                            print(f"Erro ao capturar subtítulo de {link_real}: {e}")

                        noticia_existente_db = db.query(Noticia).filter_by(title=titulo).first()
                        if noticia_existente_db:
                            continue  # pula para próxima notícia
                        else:
                            todas_noticias.append({
                                'palavra_chave': palavra,
                                'title': titulo,
                                'link': link_real,
                                'published': published,
                                'news_data': news_data
                            })

        return todas_noticias

    async def analisar_noticias_com_agente(noticias_completas, contexto):
        resultados = []
        
        sintese = contexto.get("sintese").texto if contexto.get("sintese") else HTTPException(status_code=404, detail="Síntese não encontrada")

        agent_input = f"""
            Você é um analista de crédito especializado em avaliar riscos de investimento. Sua tarefa é analisar, de forma integrada, a síntese atual da empresa {sintese} e uma notícia recente sobre ela. Com base nesses dados, você deve avaliar o impacto da notícia sobre os negócios, imagem e risco de investimento da empresa, retornando um JSON contendo os seguintes campos:
            Caso a noticia não tiver relação direta com a empresa, colocar a relevância entre 1 e 2

            - title: título da notícia.
            - relevance: número de 1 a 10 que representa o impacto da notícia nos negócios ou na imagem da empresa.
            - risc: número de 1 a 10 que representa o índice de risco para um possível investimento.
            - description: explicação detalhada do motivo da classificação atribuída.
            - published: data da publicação da notícia.

            Critérios para o campo "relevance":
            - 1 a 2: impacto baixo ou inexistente, com pouca ou nenhuma influência nos negócios ou na imagem da empresa.
            - 3 a 5: impacto moderado, com influência perceptível, mas não crítica, nos negócios ou na imagem da empresa.
            - 6 a 10: impacto alto, com influência significativa, podendo alterar substancialmente a percepção ou os resultados da empresa.

            Critérios para o campo "risc":
            - 1 a 2: risco baixo ou inexistente.
            - 3 a 5: risco moderado, ou seja, é bom tomar nota sobre essa notícia sobre essa empresa.
            - 6 a 10: risco alto, sendo 6 um risco bem considerável para a empresa e 10 indicando que a empresa pode falir amanhã.

            Observação:
            - Utilize a síntese atual da empresa para contextualizar a análise e justificar como os aspectos de tamanho, robustez e possíveis riscos sistêmicos influenciam sua avaliação.
            - O JSON de entrada e saída deve ter o mesmo comprimento.

            Formato esperado (como string JSON):
            [
                {{
                    "title": "Empresa X cresce 30% em receita durante as eleições",
                    "risc": 8,
                    "relevance": 2,
                    "description": "Considerando o impacto pontual na receita e os riscos de instabilidade política, a notícia apresenta um risco elevado, apesar de ter relevância baixa para o negócio em si.",
                    "published": "22-03-2024"
                }}
            ]

            O JSON em string, de entrada e saída devem ter o mesmo comprimento.

            Responda apenas com o array JSON convertido em string, sem explicações, comentários ou qualquer outro texto fora do JSON.
        """

        agent = Agent(name="Assistant", instructions=agent_input, model="gpt-4.1-mini")

        print(f"Agent input: {agent_input}")

        for idx, noticia in enumerate(noticias_completas):
            print(f"Analisando notícia {idx + 1}/{len(noticias_completas)}: {noticia['title']}")
            # Remove o campo 'link' antes de enviar ao agente
            noticia_sem_link = {k: v for k, v in noticia.items() if k != 'link'}
            print('Noticia:', noticia_sem_link)
            prompt = json.dumps([noticia_sem_link])  # Envia como lista com 1 item

            result = await Runner.run(agent, input=prompt)
            resultado_formatado = extrair_json_do_texto(result.final_output)

            if resultado_formatado:
                # Reinsere o link original
                resultado_formatado[0]['link'] = noticia['link']
                resultados.append(resultado_formatado[0])

        return resultados

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

    empresa = db.query(Empresa).filter(Empresa.cnpj == data.cnpj).first()
    
    if not empresa:
        raise HTTPException(status_code=400, detail="Empresa não cadastrada")

    palavras_chave = data.palavras_chave or []

    if not data.nao_incluir_nome_empresa_palavra_chave:
        palavras_chave.append(empresa.nome)

    noticias = buscar_noticias_empresa(palavras_chave, data)

    if not noticias:
        return []
    
    print(f"Encontradas {len(noticias)} notícias para a empresa {empresa.nome}")

    sintese_recente = db.query(Sintese).filter(Sintese.empresa_id == empresa.id).order_by(Sintese.data_criacao.desc()).first()
    
    print(f"Síntese recente: {sintese_recente}")

    analise = await analisar_noticias_com_agente(noticias, { "empresa": empresa, "sintese": sintese_recente })

    return analise

async def buscar_e_salvar_noticias_db(db, data: NewsScrapperSchema):

    print("Iniciando busca e salvamento de notícias...")
    noticias = await buscar_noticias_db(db, data)
    print(f"Notícias encontradas: {len(noticias)}")

    empresa = db.query(Empresa).filter(Empresa.cnpj == data.cnpj).first()
    print(f"Empresa encontrada: {empresa}")

    monitoramento = db.query(Monitoramento).filter(
        Monitoramento.empresa_id == empresa.id,
        Monitoramento.modulo == 'noticias'  # Verifica se o módulo é 'noticias'
    ).first()

    if monitoramento:
        print("Monitoramento encontrado, atualizando last_module_update...")
        monitoramento.last_module_update = datetime.now()

    if not empresa:
        print("Empresa não cadastrada, lançando exceção.")
        raise HTTPException(status_code=400, detail="Empresa não cadastrada")

    for noticia in noticias:
        print(f"Processando notícia: {noticia['title']}")
        # Verifica se a notícia já existe para a mesma empresa (por título)
        existe = db.query(Noticia).filter(
            Noticia.title == noticia["title"],
            Noticia.empresa_id == empresa.id
        ).first()

        if existe:
            print(f"Notícia já cadastrada: {noticia['title']}")
            continue

        try:
            publicada_em = datetime.strptime(noticia["published"], "%d-%m-%Y").date()
            print(f"Data de publicação convertida: {publicada_em}")
        except ValueError:
            print("Erro ao converter data de publicação, usando data atual.")
            publicada_em = date.today()

        nova_noticia = Noticia(
            title=noticia["title"],
            risc=noticia["risc"],
            relevance=noticia["relevance"],
            description=noticia["description"],
            published=publicada_em,
            link=noticia["link"],
            empresa_id=empresa.id,
        )
        
        print(f"Adicionando nova notícia ao banco de dados: {nova_noticia}")

        db.add(nova_noticia)

    db.commit()
    print("Notícias salvas com sucesso.")

    return {'message': 'Notícias salvas com sucesso.'}


async def consultar_noticias_db(db, data: GetNewsSchema):
    empresa = db.query(Empresa).filter(Empresa.cnpj == data.cnpj).first()

    if not empresa:
        raise HTTPException(status_code=400, detail="Empresa não cadastrada")

    # Query base
    query = db.query(Noticia).filter(Noticia.empresa_id == empresa.id)

    # Filtro por data
    if data.data_inicio:
        query = query.filter(Noticia.published >= data.data_inicio)
    if data.data_fim:
        query = query.filter(Noticia.published <= data.data_fim)

    # Obter as notícias
    noticias = query.order_by(Noticia.published.desc()).all()

    # Média ponderada do risco usando a relevância como peso padrão
    ponderada_query = db.query(
        func.sum(Noticia.risc * Noticia.relevance).label("soma_ponderada"),
        func.sum(Noticia.relevance).label("soma_pesos")
    ).filter(Noticia.empresa_id == empresa.id)

    if data.data_inicio:
        ponderada_query = ponderada_query.filter(Noticia.published >= data.data_inicio)
    if data.data_fim:
        ponderada_query = ponderada_query.filter(Noticia.published <= data.data_fim)

    resultado = ponderada_query.one()
    soma_ponderada = resultado.soma_ponderada or 0
    soma_pesos = resultado.soma_pesos or 1  # evita divisão por zero

    ind_risc_valor = soma_ponderada / soma_pesos

    return {
        "ind_risc": round(ind_risc_valor, 2),
        "noticias": noticias,
    }


##Palavras chave
def criar_palavra_chave_db(db, data: PalavraChaveCreateSchema):

    empresa = db.query(Empresa).filter(Empresa.cnpj == data.cnpj).first()
    if not empresa:
        raise HTTPException(status_code=400, detail="Empresa não cadastrada")

    palavra = PalavraChave(
        texto=data.texto,
        empresa_id=empresa.id
    )

    db.add(palavra)
    db.commit()
    db.refresh(palavra)
    return palavra

def listar_palavras_chave_db(db , cnpj: str):

    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()
    if not empresa:
        raise HTTPException(status_code=400, detail="Empresa não cadastrada")

    return db.query(PalavraChave).filter(PalavraChave.empresa_id == empresa.id).all()

def deletar_palavra_chave_db(db, palavra_id: int):
    palavra = db.query(PalavraChave).filter(PalavraChave.id == palavra_id).first()
    if not palavra:
        return False
    db.delete(palavra)
    db.commit()
    return True


def calcular_indice_risco_db(
    db,
    cnpj: str,
    data_inicio,
    data_fim,
):
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()

    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    resultado = db.query(
        func.sum(Noticia.risc * Noticia.relevance).label("soma_ponderada"),
        func.sum(Noticia.relevance).label("soma_pesos")
    ).filter(
        Noticia.empresa_id == empresa.id,
        Noticia.published >= data_inicio,
        Noticia.published <= data_fim
    ).one()

    if resultado.soma_pesos is None or resultado.soma_pesos == 0:
        return {
            "cnpj": cnpj,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "indice_risco": -1
        }

    soma_ponderada = resultado.soma_ponderada or 0
    soma_pesos = resultado.soma_pesos

    indice_risco = soma_ponderada / soma_pesos

    return {
        "cnpj": cnpj,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "indice_risco": round(indice_risco, 2)
    }




async def verificar_e_criar_aviso_noticias(db, cnpj: str):
    # Buscar módulo de notícias
    stmt_modulo = (
        select(Monitoramento)
        .join(Empresa, Monitoramento.empresa_id == Empresa.id)
        .where(
            func.lower(Monitoramento.modulo) == "noticias",
            Empresa.cnpj == cnpj
        )
    )
    result_modulo = db.execute(stmt_modulo)
    modulo_noticias = result_modulo.scalars().first()

    if not modulo_noticias:
        print("Módulo de notícias não encontrado.")
        return

    modulo_noticias_id = modulo_noticias.id
    hoje = date.today()

    # Verifica se já existe aviso criado hoje
    aviso_existente = db.execute(
        select(Aviso).where(
            and_(
                Aviso.classe_aviso == "variacao_diaria_indice_risco_noticias",
                Aviso.modulo_associado_id == modulo_noticias_id,
                func.date(Aviso.criado_em) == hoje
            )
        )
    ).scalars().first()

    if aviso_existente:
        print("Aviso de variação diária no índice de risco de notícias já criado hoje.")
        return

    def calcular_indice_risco_para_data(data_alvo):
        resultado = db.query(
            func.sum(Noticia.risc * Noticia.relevance).label("soma_ponderada"),
            func.sum(Noticia.relevance).label("soma_pesos")
        ).join(Empresa).filter(
            Empresa.cnpj == cnpj,
            Noticia.published == data_alvo
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
        print("Nenhuma variação de aumento de risco (>20%) nos últimos 3 dias. - noticias")
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

    mensagem = "O índice de risco de notícias " + ", e ".join(partes_mensagem) + "."

    print(mensagem)

    novo_aviso = Aviso(
        mensagem=mensagem,
        nivel_importancia=nivel_importancia,
        classe_aviso="variacao_diaria_indice_risco_noticias",
        criado_em=datetime.utcnow(),
        modulo_associado_id=modulo_noticias_id
    )

    db.add(novo_aviso)
    db.commit()
