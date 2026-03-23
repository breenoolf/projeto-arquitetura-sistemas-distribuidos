import json

async def enviar_mensagem(writer, mensagem_dict):
    """Converte um dicionário para JSON, adiciona \n e envia via socket."""
    mensagem_json = json.dumps(mensagem_dict) + "\n"
    writer.write(mensagem_json.encode())
    await writer.drain()

async def receber_mensagem(reader):
    """Lê do socket até encontrar o \n e converte de volta para dicionário."""
    linha_bytes = await reader.readline()
    if not linha_bytes:
        return None
    linha_str = linha_bytes.decode().strip()
    return json.loads(linha_str)