import json
from typing import Any, Iterable


class ProtocolError(Exception):
    """Erro de parsing/validação do protocolo (JSON por linha)."""


async def enviar_mensagem(writer, mensagem_dict: dict[str, Any]):
    """Converte um dicionário para JSON, adiciona \n e envia via socket."""
    mensagem_json = json.dumps(mensagem_dict, ensure_ascii=False) + "\n"
    writer.write(mensagem_json.encode("utf-8"))
    await writer.drain()


async def receber_mensagem(reader) -> dict[str, Any] | None:
    """Lê do socket até encontrar o \n e converte de volta para dicionário.

    Retorna None se o peer fechar a conexão.
    Lança ProtocolError se o JSON for inválido.
    """
    linha_bytes = await reader.readline()
    if not linha_bytes:
        return None
    linha_str = linha_bytes.decode("utf-8", errors="replace").strip()
    if not linha_str:
        raise ProtocolError("Linha vazia recebida")
    try:
        payload = json.loads(linha_str)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"JSON inválido: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProtocolError("Payload deve ser um objeto JSON (dict)")
    return payload


def exigir_campos(payload: dict[str, Any], campos: Iterable[str]) -> None:
    """Falha se algum campo obrigatório estiver ausente (strict parsing)."""
    ausentes = [c for c in campos if c not in payload]
    if ausentes:
        raise ProtocolError(f"Campos obrigatórios ausentes: {', '.join(ausentes)}")