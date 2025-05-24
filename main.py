import os

from fastapi import FastAPI
from database import SessionLocal, Base, engine
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from middlewares.auth import AuthMiddleware

from controller import (
    user, empresas, noticias, monitoramento, alertas,
    juridico, divida_ativa, valor_economico, protestos,
    replanilhamento, avisos,relatorios
)

Base.metadata.create_all(bind=engine)

app = FastAPI()

# Adiciona middlewares de autenticação
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "https://dealsight.netlify.app"],  # origem real do seu front-end
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message":"API EM FUNCIONAMENTO"}


#Autenticacao

app.include_router(user.router, prefix="/user", tags=["Usuário"])
app.include_router(empresas.router, prefix="/empresas", tags=["Empresas"])
app.include_router(noticias.router, prefix="/noticias", tags=["Notícias"])
app.include_router(monitoramento.router, prefix="/monitoramento", tags=["Monitoramento"])
app.include_router(alertas.router, prefix="/alertas", tags=["Alertas"])
app.include_router(juridico.router, prefix="/juridico", tags=["Jurídico"])
app.include_router(divida_ativa.router, prefix="/divida-ativa", tags=["Dívida Ativa"])
app.include_router(valor_economico.router, prefix="/valor-economico", tags=["Valor Econômico"])
app.include_router(protestos.router, prefix="/protestos", tags=["Protestos"])
app.include_router(replanilhamento.router, prefix="/replanilhamento", tags=["Replanilhamento"])
app.include_router(avisos.router, prefix="/avisos", tags=["Avisos"])
app.include_router(relatorios.router, prefix="/relatorios", tags=["Relatórios"])


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000, timeout_keep_alive=60000)


