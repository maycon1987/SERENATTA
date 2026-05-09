from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
from supabase import create_client
import os

# =========================
# ENV
# =========================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("Erro: SUPABASE_URL ou SUPABASE_KEY não configurados.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# APP
# =========================
app = FastAPI(
    title="Serenatta API",
    description="Backend da plataforma Serenatta - músicas personalizadas emocionais",
    version="1.0.0"
)

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# MODELS
# =========================
class PedidoCreate(BaseModel):
    nome_cliente: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None

    tipo_homenagem: Optional[str] = None
    nome_homenageado: Optional[str] = None

    estilo_musical: Optional[str] = None
    voz: Optional[str] = None

    qualidades: Optional[str] = None
    memorias: Optional[str] = None
    mensagem_coracao: Optional[str] = None

    plano: Optional[str] = None

    foto_url: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str


class EntregaUpdate(BaseModel):
    musica_url: Optional[str] = None
    carta_pdf_url: Optional[str] = None
    status: Optional[str] = "entregue"


# =========================
# ROTAS BASE
# =========================
@app.get("/")
def home():
    return {
        "status": "online",
        "app": "Serenatta API",
        "mensagem": "Backend da plataforma Serenatta funcionando.",
        "docs": "/docs"
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "supabase_url_ok": bool(SUPABASE_URL),
        "supabase_key_ok": bool(SUPABASE_KEY)
    }


# =========================
# CRIAR PEDIDO
# =========================
@app.post("/pedidos")
def criar_pedido(pedido: PedidoCreate):
    try:
        dados = pedido.model_dump(exclude_none=True)
        dados["status"] = "novo"

        response = supabase.table("pedidos").insert(dados).execute()

        return {
            "status": "ok",
            "mensagem": "Pedido criado com sucesso.",
            "pedido": response.data[0] if response.data else None
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# LISTAR PEDIDOS
# =========================
@app.get("/pedidos")
def listar_pedidos():
    try:
        response = (
            supabase
            .table("pedidos")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

        return {
            "status": "ok",
            "total": len(response.data),
            "pedidos": response.data
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# BUSCAR PEDIDO POR ID
# =========================
@app.get("/pedidos/{pedido_id}")
def buscar_pedido(pedido_id: str):
    try:
        response = (
            supabase
            .table("pedidos")
            .select("*")
            .eq("id", pedido_id)
            .single()
            .execute()
        )

        return {
            "status": "ok",
            "pedido": response.data
        }

    except Exception:
        raise HTTPException(status_code=404, detail="Pedido não encontrado.")


# =========================
# ATUALIZAR STATUS
# =========================
@app.patch("/pedidos/{pedido_id}/status")
def atualizar_status(pedido_id: str, dados: StatusUpdate):
    try:
        response = (
            supabase
            .table("pedidos")
            .update({"status": dados.status})
            .eq("id", pedido_id)
            .execute()
        )

        return {
            "status": "ok",
            "mensagem": "Status atualizado com sucesso.",
            "pedido": response.data[0] if response.data else None
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# ADICIONAR ENTREGA MANUAL
# =========================
@app.patch("/pedidos/{pedido_id}/entrega")
def atualizar_entrega(pedido_id: str, dados: EntregaUpdate):
    try:
        update_data = dados.model_dump(exclude_none=True)

        response = (
            supabase
            .table("pedidos")
            .update(update_data)
            .eq("id", pedido_id)
            .execute()
        )

        return {
            "status": "ok",
            "mensagem": "Entrega atualizada com sucesso.",
            "pedido": response.data[0] if response.data else None
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
