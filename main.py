from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
from supabase import create_client
import os
import re

# =========================
# ENV
# =========================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("Erro: SUPABASE_URL ou SUPABASE_KEY não configurados.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# APP
# =========================
app = FastAPI(
    title="Serenatta API",
    description="Backend da plataforma Serenatta - músicas personalizadas emocionais",
    version="1.2.0"
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
# HELPERS
# =========================
def limpar_telefone(telefone: Optional[str]) -> str:
    if not telefone:
        return ""
    return re.sub(r"\D", "", telefone)


def verificar_admin(x_admin_token: Optional[str] = Header(None)):
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_TOKEN não configurado no servidor."
        )

    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Acesso não autorizado."
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
    spotify_url: Optional[str] = None
    clipe_url: Optional[str] = None
    status: Optional[str] = "entregue"


class RevisaoCreate(BaseModel):
    revisao_solicitada: str


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
        "supabase_key_ok": bool(SUPABASE_KEY),
        "admin_token_ok": bool(ADMIN_TOKEN)
    }


# =========================
# ROTA PÚBLICA - CRIAR PEDIDO
# =========================
@app.post("/pedidos")
def criar_pedido(pedido: PedidoCreate):
    try:
        dados = pedido.model_dump(exclude_none=True)

        nome_cliente = (dados.get("nome_cliente") or "").strip()
        telefone = limpar_telefone(dados.get("telefone"))
        email = (dados.get("email") or "").strip().lower()
        plano = (dados.get("plano") or "").strip()

        if len(nome_cliente) < 2:
            raise HTTPException(
                status_code=400,
                detail="Nome do cliente é obrigatório."
            )

        if len(telefone) < 10:
            raise HTTPException(
                status_code=400,
                detail="WhatsApp válido é obrigatório."
            )

        if "@" not in email:
            raise HTTPException(
                status_code=400,
                detail="E-mail válido é obrigatório."
            )

        if len(plano) < 2:
            raise HTTPException(
                status_code=400,
                detail="Plano é obrigatório."
            )

        dados["nome_cliente"] = nome_cliente
        dados["telefone"] = telefone
        dados["email"] = email
        dados["plano"] = plano
        dados["status"] = "novo"

        response = supabase.table("pedidos").insert(dados).execute()

        return {
            "status": "ok",
            "mensagem": "Pedido criado com sucesso.",
            "pedido": response.data[0] if response.data else None
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# CLIENTE - BUSCAR PEDIDOS POR E-MAIL
# =========================
@app.get("/cliente/pedidos")
def cliente_listar_pedidos(
    email: str = Query(...),
    telefone: Optional[str] = Query(None)
):
    try:
        email_limpo = email.strip().lower()

        if "@" not in email_limpo:
            raise HTTPException(
                status_code=400,
                detail="E-mail inválido."
            )

        query = (
            supabase
            .table("pedidos")
            .select("*")
            .eq("email", email_limpo)
            .order("created_at", desc=True)
        )

        # Se o front também enviar telefone, usamos como segurança extra
        if telefone:
            telefone_limpo = limpar_telefone(telefone)
            if telefone_limpo:
                query = query.eq("telefone", telefone_limpo)

        response = query.execute()

        return {
            "status": "ok",
            "total": len(response.data or []),
            "pedidos": response.data or []
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# CLIENTE - BUSCAR UM PEDIDO ESPECÍFICO
# =========================
@app.get("/cliente/pedidos/{pedido_id}")
def cliente_buscar_pedido(
    pedido_id: str,
    email: str = Query(...)
):
    try:
        email_limpo = email.strip().lower()

        response = (
            supabase
            .table("pedidos")
            .select("*")
            .eq("id", pedido_id)
            .eq("email", email_limpo)
            .single()
            .execute()
        )

        return {
            "status": "ok",
            "pedido": response.data
        }

    except Exception:
        raise HTTPException(
            status_code=404,
            detail="Pedido não encontrado para este cliente."
        )


# =========================
# CLIENTE - SOLICITAR REVISÃO
# =========================
@app.post("/cliente/pedidos/{pedido_id}/revisao")
def cliente_solicitar_revisao(
    pedido_id: str,
    dados: RevisaoCreate,
    email: str = Query(...)
):
    try:
        email_limpo = email.strip().lower()
        texto_revisao = dados.revisao_solicitada.strip()

        if len(texto_revisao) < 10:
            raise HTTPException(
                status_code=400,
                detail="Descreva melhor o que deseja revisar."
            )

        response = (
            supabase
            .table("pedidos")
            .update({
                "revisao_solicitada": texto_revisao,
                "revisao_status": "nova",
                "status": "ajuste_solicitado"
            })
            .eq("id", pedido_id)
            .eq("email", email_limpo)
            .execute()
        )

        return {
            "status": "ok",
            "mensagem": "Solicitação de revisão enviada com sucesso.",
            "pedido": response.data[0] if response.data else None
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# ADMIN - LISTAR PEDIDOS
# =========================
@app.get("/admin/pedidos")
def admin_listar_pedidos(x_admin_token: Optional[str] = Header(None)):
    verificar_admin(x_admin_token)

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
            "total": len(response.data or []),
            "pedidos": response.data or []
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# ADMIN - BUSCAR PEDIDO POR ID
# =========================
@app.get("/admin/pedidos/{pedido_id}")
def admin_buscar_pedido(
    pedido_id: str,
    x_admin_token: Optional[str] = Header(None)
):
    verificar_admin(x_admin_token)

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
# ADMIN - ATUALIZAR STATUS
# =========================
@app.patch("/admin/pedidos/{pedido_id}/status")
def admin_atualizar_status(
    pedido_id: str,
    dados: StatusUpdate,
    x_admin_token: Optional[str] = Header(None)
):
    verificar_admin(x_admin_token)

    try:
        status_permitidos = [
            "novo",
            "em_analise",
            "em_producao",
            "aguardando_aprovacao",
            "ajuste_solicitado",
            "aprovado",
            "entregue",
            "cancelado"
        ]

        if dados.status not in status_permitidos:
            raise HTTPException(
                status_code=400,
                detail=f"Status inválido. Use um destes: {status_permitidos}"
            )

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

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# ADMIN - ADICIONAR ENTREGA
# =========================
@app.patch("/admin/pedidos/{pedido_id}/entrega")
def admin_atualizar_entrega(
    pedido_id: str,
    dados: EntregaUpdate,
    x_admin_token: Optional[str] = Header(None)
):
    verificar_admin(x_admin_token)

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


# =========================
# ADMIN - ATUALIZAR REVISÃO
# =========================
@app.patch("/admin/pedidos/{pedido_id}/revisao-status")
def admin_atualizar_revisao_status(
    pedido_id: str,
    dados: StatusUpdate,
    x_admin_token: Optional[str] = Header(None)
):
    verificar_admin(x_admin_token)

    try:
        revisao_status_permitidos = [
            "nova",
            "em_analise",
            "em_ajuste",
            "concluida",
            "recusada"
        ]

        if dados.status not in revisao_status_permitidos:
            raise HTTPException(
                status_code=400,
                detail=f"Status de revisão inválido. Use um destes: {revisao_status_permitidos}"
            )

        response = (
            supabase
            .table("pedidos")
            .update({"revisao_status": dados.status})
            .eq("id", pedido_id)
            .execute()
        )

        return {
            "status": "ok",
            "mensagem": "Status da revisão atualizado com sucesso.",
            "pedido": response.data[0] if response.data else None
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# ADMIN - DASHBOARD RESUMO
# =========================
@app.get("/admin/dashboard")
def admin_dashboard(x_admin_token: Optional[str] = Header(None)):
    verificar_admin(x_admin_token)

    try:
        response = (
            supabase
            .table("pedidos")
            .select("*")
            .execute()
        )

        pedidos = response.data or []

        resumo_status = {}
        resumo_planos = {}
        revisoes_pendentes = 0

        for pedido in pedidos:
            status = pedido.get("status") or "sem_status"
            plano = pedido.get("plano") or "sem_plano"

            resumo_status[status] = resumo_status.get(status, 0) + 1
            resumo_planos[plano] = resumo_planos.get(plano, 0) + 1

            if pedido.get("revisao_status") in ["nova", "em_analise", "em_ajuste"]:
                revisoes_pendentes += 1

        return {
            "status": "ok",
            "total_pedidos": len(pedidos),
            "revisoes_pendentes": revisoes_pendentes,
            "por_status": resumo_status,
            "por_plano": resumo_planos,
            "ultimos_pedidos": pedidos[:5]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
