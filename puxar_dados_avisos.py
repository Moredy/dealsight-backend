from database import SessionLocal
from service.monitoramento import executar_cron_para_todas_avisos_empresas
import asyncio

async def executar_cron():
    db = SessionLocal()
    await executar_cron_para_todas_avisos_empresas(db)

if __name__ == "__main__":
    asyncio.run(executar_cron())
