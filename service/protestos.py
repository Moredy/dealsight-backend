
import requests
import time
from datetime import datetime

from model.models import Protesto, Empresa
from schemas.protestos import ProtestoData
from agents import Agent, Runner  # Supondo que você já tenha essas classes
import json
import re
from model.models import Empresa, Processo, Sintese, ClassificacaoProcesso, Aviso, Monitoramento

from datetime import datetime,timedelta



CONSULTA_URL = "https://consulta-protesto-api-896dec77750f.herokuapp.com/consultar/"
RESULTADO_URL = "https://consulta-protesto-api-896dec77750f.herokuapp.com/resultado/"

def extrair_json_do_texto(texto: str):
    try:
        return json.loads(texto)
    except json.JSONDecodeError as e:
        print(f"Erro ao decodificar JSON: {e}")
        return {}

async def consultar_gravar_protestos_por_cnpj_db(cnpj: str, db, intervalo=5, timeout=160):
    """
    Consulta protesto por CNPJ, aguarda resultado e salva no banco se concluído.
    Também analisa o risco e a relevância usando IA antes de salvar.
    """
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()

    if not empresa:
        raise ValueError(f"Empresa com CNPJ {cnpj} não encontrada no banco de dados.")

    cnpj = empresa.cnpj

    try:
        print(f"📨 Enviando consulta para o CNPJ {cnpj}...")
        response = requests.post(CONSULTA_URL + cnpj)
        response.raise_for_status()
        job_id = response.json().get("jobId")

        if not job_id:
            raise RuntimeError("jobId não retornado pela API.")

        print(f"⌛ Aguardando resultado para jobId {job_id}...")

        tempo_total = 0
        while tempo_total < timeout:
            result_response = requests.get(RESULTADO_URL + job_id)
            result_response.raise_for_status()
            result_data = result_response.json()

            status = result_data.get("status")
            if status == "Concluído":
                resultado = result_data.get("resultado")
                print("✅ Consulta concluída. Iniciando análise de IA...")

                # Construir prompt para IA
                sintese_recente = db.query(Sintese).filter(Sintese.empresa_id == empresa.id).order_by(Sintese.data_criacao.desc()).first()

                agent_input = f"""
                Você é um analista de risco especializado. Avalie os protestos listados abaixo com base na sua quantidade, datas, valores e impacto potencial à empresa {sintese_recente}.

                Responda com um JSON contendo:
                - "relevancia": de 1 a 10
                - "risco": de 1 a 10
                - "justificativa": breve explicação

                Retorne apenas o JSON em string.
                """

                prompt_input = json.dumps([result_data])

                # Limite de caracteres do gpt
                max_chars = 100_000
                if len(prompt_input) > max_chars:
                    prompt_input = prompt_input[:max_chars]

                agent = Agent(name="ProtestAnalyzer", instructions=agent_input, model="gpt-4.1-mini")
                result =  await Runner.run(agent, input=prompt_input)

                print("🧠 IA respondeu:", result.final_output)

                output = extrair_json_do_texto(result.final_output)

                relevancia = output.get("relevancia", -1)
                risco = output.get("risco", -1)
                justificativa = output.get("justificativa", -1)


                protesto = Protesto(
                    json_consulta_cenprot=resultado,
                    empresa_id=empresa.id,
                    qtd_titulos=resultado.get("qtdTitulos", 0),
                    data_consulta=datetime.strptime(resultado.get("dataConsulta"), "%d/%m/%Y %H:%M"),
                    relevancia=relevancia,
                    risco=risco,
                    justificativa=justificativa
                )

                db.add(protesto)
                db.commit()
                db.refresh(protesto)
                print("📝 Consulta salva com sucesso.")
                return protesto

            print(f"⏳ Status: {status} | Aguardando {intervalo} segundos...")
            time.sleep(intervalo)
            tempo_total += intervalo

        raise TimeoutError("Tempo limite excedido sem conclusão da consulta.")

    except Exception as e:
        raise RuntimeError(f"Erro durante a consulta ou inserção: {e}")


def buscar_protesto_mais_recente_por_cnpj_db(cnpj: str, db):
    """
    Retorna o protesto mais recente da empresa com o CNPJ informado.
    """
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()

    if not empresa:
        return {"erro": "Empresa não encontrada"}

    protesto = (
        db.query(Protesto)
        .filter(Protesto.empresa_id == empresa.id)
        .order_by(Protesto.data_consulta.desc())
        .first()
    )

    if not protesto:
        return {"mensagem": "Nenhum protesto encontrado para esta empresa."}

    return protesto

def calcular_risco_relevancia_medio_db(cnpj: str, db):
    """
    Retorna a média entre risco e relevância do protesto mais recente da empresa com o CNPJ informado.
    """
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()

    if not empresa:
        return -1  # ou pode retornar None ou lançar uma exceção

    protesto = (
        db.query(Protesto)
        .filter(Protesto.empresa_id == empresa.id)
        .order_by(Protesto.data_consulta.desc())
        .first()
    )

    if not protesto or protesto.risco is None or protesto.relevancia is None:
        return -1  # ou outro valor padrão

    media = (protesto.risco + protesto.relevancia) / 2
    return {"indice_risco": media}
