from sqlalchemy.orm import Mapped, mapped_column,relationship
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime,Date,Text, func, Float, Boolean, BigInteger, JSON
from database import Base
from datetime import datetime
from sqlalchemy import UniqueConstraint
from datetime import datetime, timezone


class OrganizacaoEmpresa(Base):
    __tablename__ = "organizacoes_empresas"

    id = Column(Integer, primary_key=True)
    organizacao_id = Column(Integer, ForeignKey("organizacoes.id", ondelete="CASCADE"), nullable=False)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (
        UniqueConstraint("organizacao_id", "empresa_id", name="uix_organizacao_empresa"),
    )

class Organizacao(Base):
    __tablename__ = "organizacoes"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)

    usuarios = relationship("User", back_populates="organizacao", cascade="all, delete")
    empresas = relationship(
        "Empresa",
        secondary="organizacoes_empresas",
        back_populates="organizacoes"
    )

    replanilhamentos = relationship(
        "ReplanilhamentoHistorico",
        back_populates="organizacao",
        cascade="all, delete-orphan",
        passive_deletes=True
    )


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    firstName: Mapped[str] = mapped_column(String(20), nullable=False)
    lastName: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    cel: Mapped[str] = mapped_column(String(11), nullable=False)
    password: Mapped[str] = mapped_column(String(55), nullable=False)
    gender: Mapped[str] = mapped_column(String(20), nullable=False)
    two_factor_associated = mapped_column(Boolean, nullable=False)

    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")

    organizacao_id = Column(Integer, ForeignKey("organizacoes.id", ondelete="SET NULL"), nullable=True)
    organizacao = relationship("Organizacao", back_populates="usuarios")

class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    type = Column(String)
    token = Column(String, unique=True, index=True)
    created_at = Column(DateTime)
    expires_at = Column(DateTime)

    user = relationship("User", back_populates="sessions")

class ReplanilhamentoHistorico(Base):
    __tablename__ = "replanilhamento_historico"

    id = Column(Integer, primary_key=True, index=True)
    ms_replanning_request_id = Column(String, nullable=False)
    cnpj = Column(String, nullable=False)
    tipo = Column(String, nullable=False)
    data_upload = Column(DateTime, default=datetime.utcnow)
    responsavel = Column(String, nullable=False)

    organizacao_id = Column(
        Integer,
        ForeignKey("organizacoes.id", ondelete="CASCADE"),
        nullable=False
    )
    organizacao = relationship("Organizacao", back_populates="replanilhamentos", passive_deletes=True)


class Empresa(Base):
    __tablename__ = "empresas"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(255), nullable=False)
    nome_fantasia = Column(Text, nullable=True)
    cnpj = Column(String(20), unique=True, nullable=False, index=True)
    atividade_principal = Column(Text)
    atividade_principal_id = Column(Integer)
    monitoramento_ativo = Column(Boolean, default=True)

    organizacoes = relationship(
        "Organizacao",
        secondary="organizacoes_empresas",
        back_populates="empresas"
    )

    processos = relationship(
        "Processo",
        back_populates="empresa",
        cascade="all, delete-orphan"
    )
    dividas_ativas_sp = relationship("DividaAtivaSp", back_populates="empresa", cascade="all, delete-orphan")
    dividas_ativas_uniao = relationship("DividaAtivaUniao", back_populates="empresa", cascade="all, delete-orphan")
    noticias = relationship("Noticia", back_populates="empresa", cascade="all, delete-orphan")
    socios = relationship("Socio", back_populates="empresa", cascade="all, delete-orphan")
    palavras_chave = relationship("PalavraChave", back_populates="empresa", cascade="all, delete-orphan")
    monitoramento = relationship("Monitoramento", back_populates="empresa", cascade="all, delete", uselist=False)
    alertas = relationship("Alerta", back_populates="empresa", cascade="all, delete-orphan", passive_deletes=True)
    sinteses = relationship("Sintese", back_populates="empresa", cascade="all, delete-orphan")

    protestos = relationship("Protesto", back_populates="empresa", cascade="all, delete")

class Sintese(Base):
    __tablename__ = "sinteses"
    
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"))
    texto = Column(Text, nullable=False)
    data_criacao = Column(Date, nullable=False, default=lambda: datetime.now(timezone.utc))
    
    empresa = relationship("Empresa", back_populates="sinteses")

class Socio(Base):
    __tablename__ = "socios"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"))
    nome = Column(String(255), nullable=False)
    cargo = Column(String(100))
    desde = Column(Date)

    empresa = relationship("Empresa", back_populates="socios")

class Noticia(Base):
    __tablename__ = "noticias"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    risc = Column(Integer, nullable=False)
    relevance = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    published = Column(Date, nullable=False)
    link = Column(Text, nullable=False)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)

    empresa = relationship("Empresa", back_populates="noticias")

class PalavraChave(Base):
    __tablename__ = "palavras_chave"

    id = Column(Integer, primary_key=True, index=True)
    texto = Column(String(100), nullable=False)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)

    empresa = relationship("Empresa", back_populates="palavras_chave")


class Monitoramento(Base):
    __tablename__ = 'monitoramentos'

    id = Column(Integer, primary_key=True)
    modulo = Column(String)
    frequencia = Column(String)
    empresa_id = Column(Integer, ForeignKey('empresas.id', ondelete='CASCADE'))
    empresa = relationship("Empresa", back_populates="monitoramento")
    last_module_update = Column(DateTime, default=func.now())  # Apenas na criação

    build_statuses = relationship("BuildStatusModel", back_populates="monitoramento", cascade="all, delete-orphan",
                                  passive_deletes=True)


class Alerta(Base):
    __tablename__ = "alertas"

    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False)
    module_name = Column(String, nullable=False)
    contact_method = Column(String, nullable=False)
    indice_min = Column(Float, nullable=False)

    empresa = relationship("Empresa", back_populates="alertas")

class LogsDisparoAlertas(Base):
    __tablename__ = "logs_disparo_alertas"

    id = Column(Integer, primary_key=True, index=True)
    data = Column(DateTime, default=datetime.now)

    # Nome do módulo que disparou o alerta
    modulo_name = Column(String, nullable=False)

    # Nome da empresa no momento do disparo
    empresa_nome = Column(String, nullable=False)

    # CNPJ da empresa no momento do disparo (sem ForeignKey) Para nao gerar interdependencia
    cnpj = Column(String(20), nullable=False)

    # Índice mínimo relacionado ao alerta
    indice_min = Column(Float, nullable=False)

class Processo(Base):
    __tablename__ = 'processos'

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(String)
    vara = Column(String)
    valor = Column(Float, nullable=True)

    ultimo_andamento_tipo= Column(Integer, nullable=True)
    ultimo_andamento_content= Column(String, nullable=True)
    ultimo_andamento_data = Column(Date, nullable=True)

    resumo= Column(String, nullable=True)

    risc = Column(Integer, nullable=False)
    relevance = Column(Integer, nullable=False)
    description = Column(String)
    comarca = Column(String)
    assunto = Column(String)
    data_distribuicao = Column(Date, nullable=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    empresa = relationship(
        "Empresa",
        back_populates="processos"
    )

    classificacoes = relationship("ClassificacaoProcesso", back_populates="processo", cascade="all, delete-orphan")


class ClassificacaoProcesso(Base):
    __tablename__ = "classificacoes_processos"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    code = Column(BigInteger, nullable=False)
    process_sphere=Column(String, nullable=False)
    processo_id = Column(Integer, ForeignKey("processos.id"), nullable=False)

    processo = relationship("Processo", back_populates="classificacoes")


class DividaAtivaUniao(Base):
    __tablename__ = "dividas_ativas_uniao"

    id = Column(Integer, primary_key=True, index=True)

    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False)
    total_divida = Column(Float, nullable=False)
    risco = Column(Float,  nullable=False)
    relevancia =  Column(Float, nullable=False)
    descricao = Column(String, nullable=False)
    data_consulta = Column(DateTime, default=datetime.utcnow, nullable=False)

    empresa = relationship("Empresa", back_populates="dividas_ativas_uniao", passive_deletes=True)

class DividaAtivaSp(Base):
    __tablename__ = "dividas_ativas_sp"

    id = Column(Integer, primary_key=True, index=True)

    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False)
    total_divida = Column(Float, nullable=False)
    origem = Column(String)
    risco = Column(Float,  nullable=False)
    relevancia =  Column(Float, nullable=False)
    descricao = Column(String, nullable=False)
    tipo = Column(String)
    quantidade = Column(Integer, nullable=False)
    data_consulta = Column(DateTime, default=datetime.utcnow, nullable=False)

    empresa = relationship("Empresa", back_populates="dividas_ativas_sp", passive_deletes=True)

class NoticiaValorEconomico(Base):
    __tablename__ = "noticias_valor_economico"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(Text, nullable=True)
    empresa = Column(String, nullable=True)
    cnpj = Column(String, nullable=True)
    endereco = Column(String, nullable=True)
    risco = Column(Float,  nullable=False)
    relevancia =  Column(Float, nullable=False)
    descricao = Column(String, nullable=False)
    administrador_judicial = Column(String, nullable=True)
    vara_comarca = Column(String, nullable=True)
    observacao = Column(String, nullable=True)
    data_publicacao = Column(String, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('titulo', 'cnpj', 'data_publicacao', name='uix_titulo_cnpj_data'),
    )

class Aviso(Base):
    __tablename__ = "avisos"

    id = Column(Integer, primary_key=True, index=True)

    mensagem = Column(Text, nullable=False)
    nivel_importancia = Column(Integer, nullable=False)
    classe_aviso = Column(String, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow)

    modulo_associado_id = Column(Integer, ForeignKey("monitoramentos.id", ondelete="SET NULL"), nullable=True)
    modulo_associado = relationship("Monitoramento", backref="avisos")


class BuildStatusModel(Base):
    __tablename__ = "build_statuses"

    request_id = Column(String, primary_key=True)
    status = Column(String, nullable=False)
    progress = Column(Integer, default=0)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    errors = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Nova coluna com a foreign key
    monitoramento_id = Column(
        Integer,
        ForeignKey("monitoramentos.id", ondelete="CASCADE"),
        nullable=True
    )

    monitoramento = relationship("Monitoramento", back_populates="build_statuses", passive_deletes=False)


class Protesto(Base):
    __tablename__ = "protestos"

    id = Column(Integer, primary_key=True, index=True)
    json_consulta_cenprot = Column(JSON, nullable=False)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False)
    qtd_titulos = Column(Integer, nullable=False)
    data_consulta = Column(DateTime, default=datetime.utcnow)
    risco = Column(Float,  nullable=False)
    relevancia =  Column(Float, nullable=False)
    justificativa = Column(String, nullable=False)

    empresa = relationship("Empresa", back_populates="protestos")