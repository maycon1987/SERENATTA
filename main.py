from fastapi import FastAPI, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from supabase import create_client
import os
import re
import requests
import uuid
from datetime import datetime, timezone

# =========================
# ENV
# =========================
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
MERCADO_PAGO_ACCESS_TOKEN = os.getenv("MERCADO_PAGO_ACCESS_TOKEN")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("Erro: SUPABASE_URL ou SUPABASE_KEY não configurados.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# APP
# =========================
app = FastAPI(
    title="Serenatta API",
    description="Backend da plataforma Serenatta - músicas personalizadas emocionais",
    version="1.3.0"
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


def validar_pedido_basico(dados: Dict[str, Any]):
    nome_cliente = (dados.get("nome_cliente") or "").strip()
    telefone = limpar_telefone(dados.get("telefone"))
    email = (dados.get("email") or "").strip().lower()
    plano = (dados.get("plano") or "").strip()

    if len(nome_cliente) < 2:
        raise HTTPException(status_code=400, detail="Nome do cliente é obrigatório.")

    if len(telefone) < 10:
        raise HTTPException(status_code=400, detail="WhatsApp válido é obrigatório.")

    if "@" not in email:
        raise HTTPException(status_code=400, detail="E-mail válido é obrigatório.")

    if len(plano) < 2:
        raise HTTPException(status_code=400, detail="Plano é obrigatório.")

    dados["nome_cliente"] = nome_cliente
    dados["telefone"] = telefone
    dados["email"] = email
    dados["plano"] = plano

    return dados


def mercado_pago_headers():
    if not MERCADO_PAGO_ACCESS_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="MERCADO_PAGO_ACCESS_TOKEN não configurado no servidor."
        )

    return {
        "Authorization": f"Bearer {MERCADO_PAGO_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": str(uuid.uuid4())
    }


def atualizar_pagamento_no_supabase(payment_id: str):
    try:
        url = f"https://api.mercadopago.com/v1/payments/{payment_id}"

        headers = {
            "Authorization": f"Bearer {MERCADO_PAGO_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        mp_response = requests.get(url, headers=headers, timeout=20)

        if mp_response.status_code >= 400:
            raise HTTPException(
                status_code=mp_response.status_code,
                detail=mp_response.text
            )

        pagamento = mp_response.json()

        status_mp = pagamento.get("status")
        external_reference = pagamento.get("external_reference")
        metodo_pagamento = pagamento.get("payment_method_id")
        valor = pagamento.get("transaction_amount")

        update_data = {
            "pagamento_status": status_mp,
            "mercado_pago_payment_id": str(payment_id),
            "metodo_pagamento": metodo_pagamento,
            "valor": valor
        }

        if status_mp == "approved":
            update_data["pago_em"] = datetime.now(timezone.utc).isoformat()

        if external_reference:
            supabase.table("pedidos").update(update_data).eq("id", external_reference).execute()
        else:
            supabase.table("pedidos").update(update_data).eq("mercado_pago_payment_id", str(payment_id)).execute()

        return pagamento

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


class PagamentoPixCreate(BaseModel):
    pedido: PedidoCreate


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
        "admin_token_ok": bool(ADMIN_TOKEN),
        "mercado_pago_token_ok": bool(MERCADO_PAGO_ACCESS_TOKEN)
    }


# =========================
# ROTA PÚBLICA - CRIAR PEDIDO SEM PAGAMENTO
# =========================
@app.post("/pedidos")
def criar_pedido(pedido: PedidoCreate):
    try:
        dados = pedido.model_dump(exclude_none=True)
        dados = validar_pedido_basico(dados)

        dados["status"] = "novo"
        dados["valor"] = 79.00
        dados["pagamento_status"] = "pendente"

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
# PAGAMENTO PIX - MERCADO PAGO
# =========================
@app.post("/pagamentos/pix")
def criar_pagamento_pix(payload: PagamentoPixCreate):
    try:
        pedido_dados = payload.pedido.model_dump(exclude_none=True)
        pedido_dados = validar_pedido_basico(pedido_dados)

        pedido_dados["status"] = "novo"
        pedido_dados["valor"] = 79.00
        pedido_dados["pagamento_status"] = "pendente"
        pedido_dados["metodo_pagamento"] = "pix"

        pedido_response = supabase.table("pedidos").insert(pedido_dados).execute()

        if not pedido_response.data:
            raise HTTPException(status_code=500, detail="Erro ao criar pedido no Supabase.")

        pedido_criado = pedido_response.data[0]
        pedido_id = pedido_criado["id"]

        nome_cliente = pedido_dados.get("nome_cliente", "Cliente Serenatta")
        email_cliente = pedido_dados.get("email")
        telefone_cliente = pedido_dados.get("telefone")

        mp_payload = {
            "transaction_amount": 79.00,
            "description": "Serenatta - Música personalizada Promoção Dia dos Namorados",
            "payment_method_id": "pix",
            "external_reference": pedido_id,
            "payer": {
                "email": email_cliente,
                "first_name": nome_cliente,
            },
            "metadata": {
                "pedido_id": pedido_id,
                "telefone": telefone_cliente,
                "produto": "Serenatta - Música personalizada",
                "plano": "Promoção Dia dos Namorados"
            }
        }

        mp_response = requests.post(
            "https://api.mercadopago.com/v1/payments",
            headers=mercado_pago_headers(),
            json=mp_payload,
            timeout=30
        )

        if mp_response.status_code >= 400:
            supabase.table("pedidos").update({
                "pagamento_status": "erro_mercado_pago"
            }).eq("id", pedido_id).execute()

            raise HTTPException(
                status_code=mp_response.status_code,
                detail=mp_response.text
            )

        pagamento = mp_response.json()
        payment_id = str(pagamento.get("id"))
        status_mp = pagamento.get("status")

        supabase.table("pedidos").update({
            "mercado_pago_payment_id": payment_id,
            "pagamento_status": status_mp,
            "metodo_pagamento": "pix"
        }).eq("id", pedido_id).execute()

        transaction_data = (
            pagamento
            .get("point_of_interaction", {})
            .get("transaction_data", {})
        )

        return {
            "status": "ok",
            "mensagem": "Pagamento Pix criado com sucesso.",
            "pedido": pedido_criado,
            "pedido_id": pedido_id,
            "payment_id": payment_id,
            "payment_status": status_mp,
            "qr_code": transaction_data.get("qr_code"),
            "qr_code_base64": transaction_data.get("qr_code_base64"),
            "copia_e_cola": transaction_data.get("qr_code"),
            "ticket_url": transaction_data.get("ticket_url")
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# CONSULTAR STATUS DO PAGAMENTO
# =========================
@app.get("/pagamentos/{payment_id}/status")
def consultar_status_pagamento(payment_id: str):
    try:
        pagamento = atualizar_pagamento_no_supabase(payment_id)

        return {
            "status": "ok",
            "payment_id": str(pagamento.get("id")),
            "payment_status": pagamento.get("status"),
            "status_detail": pagamento.get("status_detail"),
            "external_reference": pagamento.get("external_reference"),
            "transaction_amount": pagamento.get("transaction_amount"),
            "payment_method_id": pagamento.get("payment_method_id")
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# WEBHOOK MERCADO PAGO
# =========================
@app.post("/webhooks/mercadopago")
async def webhook_mercado_pago(request: Request):
    try:
        body = await request.json()

        payment_id = None

        if isinstance(body, dict):
            data = body.get("data") or {}
            payment_id = data.get("id") or body.get("id")

        if not payment_id:
            return {
                "status": "ignored",
                "mensagem": "Webhook recebido sem payment_id.",
                "body": body
            }

        pagamento = atualizar_pagamento_no_supabase(str(payment_id))

        return {
            "status": "ok",
            "mensagem": "Webhook processado com sucesso.",
            "payment_id": str(payment_id),
            "payment_status": pagamento.get("status")
        }

    except Exception as e:
        return {
            "status": "error",
            "detail": str(e)
        }


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
            raise HTTPException(status_code=400, detail="E-mail inválido.")

        query = (
            supabase
            .table("pedidos")
            .select("*")
            .eq("email", email_limpo)
            .order("created_at", desc=True)
        )

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
        resumo_pagamentos = {}
        revisoes_pendentes = 0

        for pedido in pedidos:
            status = pedido.get("status") or "sem_status"
            plano = pedido.get("plano") or "sem_plano"
            pagamento_status = pedido.get("pagamento_status") or "sem_pagamento"

            resumo_status[status] = resumo_status.get(status, 0) + 1
            resumo_planos[plano] = resumo_planos.get(plano, 0) + 1
            resumo_pagamentos[pagamento_status] = resumo_pagamentos.get(pagamento_status, 0) + 1

            if pedido.get("revisao_status") in ["nova", "em_analise", "em_ajuste"]:
                revisoes_pendentes += 1

        return {
            "status": "ok",
            "total_pedidos": len(pedidos),
            "revisoes_pendentes": revisoes_pendentes,
            "por_status": resumo_status,
            "por_plano": resumo_planos,
            "por_pagamento": resumo_pagamentos,
            "ultimos_pedidos": pedidos[:5]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
