"""Fonte de dados: robô "Google Flights API" (lergassy) na Apify.

Toda a conversa com a Apify fica neste arquivo. Para trocar de fonte, crie outro
módulo com uma função `buscar_ida(cfg) -> list[dict]` que devolva opções no mesmo
formato de `normalizar()` e aponte `busca.fonte` no config.toml para ele.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ATOR = "lergassy~google-flights-api"
API = "https://api.apify.com/v2"
TEMPO_MAXIMO_S = 15 * 60


def _chamar(metodo, caminho, token, corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(
        f"{API}{caminho}",
        data=dados,
        method=metodo,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Apify respondeu {e.code} em {caminho}: {detalhe}") from None


def montar_entrada(cfg):
    v, b = cfg["viagem"], cfg["busca"]
    return {
        "routes": [
            {"origin": v["origem"], "destination": v["destino"], "departureDate": d}
            for d in v["datas"]
        ],
        "adults": v["adultos"],
        "cabinClass": "economy",
        "currency": v["moeda"],
        "market": "BR",
        "language": "pt-BR",
        "maxResults": b["resultados_por_data"],
        "sortBy": "best",
        "maxStops": str(b["max_conexoes"]),
        "resolveBookingOptions": b["links_de_compra_top"] > 0,
        "maxBookingResolutions": b["links_de_compra_top"],
        "includePriceInsights": False,
        "includeRunSummary": False,
    }


def buscar_brutos(cfg):
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN não configurado (GitHub Secrets).")

    run = _chamar("POST", f"/acts/{ATOR}/runs", token, montar_entrada(cfg))["data"]
    inicio = time.time()
    while run["status"] in ("READY", "RUNNING"):
        if time.time() - inicio > TEMPO_MAXIMO_S:
            raise RuntimeError("A busca na Apify passou de 15 minutos.")
        time.sleep(10)
        run = _chamar("GET", f"/actor-runs/{run['id']}", token)["data"]
    if run["status"] != "SUCCEEDED":
        raise RuntimeError(f"A busca na Apify terminou com status {run['status']}.")

    itens = _chamar("GET", f"/datasets/{run['defaultDatasetId']}/items?clean=true&format=json", token)
    return [i for i in itens if i.get("type") in (None, "flight")]


def buscar_ida(cfg):
    brutos = buscar_brutos(cfg)
    # Guarda a resposta crua da última rodada para conferir os campos se algo vier estranho.
    copia = Path(__file__).resolve().parent.parent / "data" / "ultima_resposta_apify.json"
    copia.parent.mkdir(parents=True, exist_ok=True)
    copia.write_text(json.dumps(brutos, ensure_ascii=False, indent=1), encoding="utf-8")
    opcoes = []
    for bruto in brutos:
        try:
            op = normalizar(bruto, cfg)
        except Exception as e:  # um item estranho não derruba a rodada inteira
            print(f"Aviso: item ignorado ({e})")
            continue
        if op:
            opcoes.append(op)
    return opcoes


# ---------------------------------------------------------------------------
# Normalização: o formato do robô não é 100% documentado, então cada campo é
# procurado por vários nomes possíveis.


def _pegar(d, *chaves, padrao=None):
    if not isinstance(d, dict):
        return padrao
    for c in chaves:
        if d.get(c) not in (None, "", []):
            return d[c]
    return padrao


def _codigo_aeroporto(valor):
    if isinstance(valor, dict):
        return _pegar(valor, "code", "id", "iata", "airportCode")
    return valor


def _aeroporto(trecho, lado):
    if lado == "saida":
        valor = _pegar(trecho, "departureAirport", "from", "origin", "departureAirportCode", "departure")
    else:
        valor = _pegar(trecho, "arrivalAirport", "to", "destination", "arrivalAirportCode", "arrival")
    return _codigo_aeroporto(valor)


def _hora(valor):
    if isinstance(valor, dict):
        valor = _pegar(valor, "time", "dateTime", "at")
    if not valor:
        return None
    return str(valor).replace(" ", "T")[:16]


def _minutos(valor):
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return int(valor)
    texto = str(valor).lower()
    h = re.search(r"(\d+)\s*h", texto)
    m = re.search(r"(\d+)\s*m", texto)
    if h or m:
        return int(h.group(1) if h else 0) * 60 + int(m.group(1) if m else 0)
    return int(texto) if texto.isdigit() else None


def _diferenca_min(inicio, fim):
    from datetime import datetime

    try:
        return int((datetime.fromisoformat(fim) - datetime.fromisoformat(inicio)).total_seconds() // 60)
    except (TypeError, ValueError):
        return None


def _mala(valor):
    if valor is None:
        return "verificar"
    if isinstance(valor, bool):
        return "sim" if valor else "nao"
    try:
        return "sim" if float(valor) > 0 else "nao"
    except (TypeError, ValueError):
        return "verificar"


def _link_compra(bruto, companhias):
    opcoes = bruto.get("bookingOptions") or []
    melhor = None
    for o in opcoes:
        url = _pegar(o, "deepLink", "url", "link", "bookingUrl")
        if not url:
            continue
        vendedor = _pegar(o, "seller", "bookWith", "name", padrao="")
        candidato = {"url": url, "vendedor": vendedor, "da_companhia": any(
            c and c.lower() in str(vendedor).lower() for c in companhias)}
        if candidato["da_companhia"]:
            return candidato
        melhor = melhor or candidato
    return melhor


def normalizar(bruto, cfg):
    preco = _pegar(bruto, "price", "totalPrice")
    if preco is None:
        return None
    preco = float(preco)
    adultos = cfg["viagem"]["adultos"]

    trechos = []
    for leg in bruto.get("legs") or []:
        trechos.append({
            "voo": _pegar(leg, "flightNumber", "flight_number", "number"),
            "companhia": _pegar(leg, "airline", "operatingCarrier", "carrier", "marketingCarrier"),
            "de": _aeroporto(leg, "saida"),
            "para": _aeroporto(leg, "chegada"),
            "partida": _hora(_pegar(leg, "departAt", "departureTime", "departure")),
            "chegada": _hora(_pegar(leg, "arriveAt", "arrivalTime", "arrival")),
        })

    escalas = []
    layovers = bruto.get("layovers") or []
    for i in range(max(len(trechos) - 1, len(layovers))):
        lay = layovers[i] if i < len(layovers) else {}
        chegou = trechos[i]["para"] if i + 1 < len(trechos) else None
        saiu = trechos[i + 1]["de"] if i + 1 < len(trechos) else None
        duracao = _minutos(_pegar(lay, "durationMinutes", "duration"))
        if duracao is None and i + 1 < len(trechos):
            duracao = _diferenca_min(trechos[i]["chegada"], trechos[i + 1]["partida"])
        escalas.append({
            "aeroporto": _codigo_aeroporto(_pegar(lay, "airport", "id", "code")) or chegou,
            "cidade": _pegar(lay, "city", "name"),
            "duracao_min": duracao,
            "troca_aeroporto": bool(chegou and saiu and chegou != saiu),
        })

    companhias = []
    for c in [t["companhia"] for t in trechos] or [bruto.get("airline")]:
        if c and c not in companhias:
            companhias.append(c)

    voos = [t["voo"] for t in trechos if t["voo"]] or list(bruto.get("flightNumbers") or [])
    partida = _hora(bruto.get("departAt")) or (trechos[0]["partida"] if trechos else None)
    chegada = _hora(bruto.get("arriveAt")) or (trechos[-1]["chegada"] if trechos else None)
    data = (partida or "")[:10]
    if data not in cfg["viagem"]["datas"]:
        return None

    compra = _link_compra(bruto, companhias)
    return {
        "id": f"{data}|{'-'.join(v.replace(' ', '') for v in voos)}",
        "data": data,
        "companhias": companhias,
        "voos": voos,
        "partida": partida,
        "chegada": chegada,
        "duracao_min": _minutos(_pegar(bruto, "totalDurationMinutes", "totalDuration", "duration")),
        "conexoes": int(_pegar(bruto, "stops", padrao=len(escalas))),
        "escalas": escalas,
        "trechos": trechos,
        "mala_de_mao": _mala(bruto.get("carryOnBagsIncluded")),
        "preco_total": round(preco, 2),
        "preco_pessoa": round(preco / adultos, 2),
        "link": compra["url"] if compra else bruto.get("googleFlightsUrl"),
        "link_tipo": ("companhia" if compra["da_companhia"] else "vendedor") if compra else "google",
        "vendedor": compra["vendedor"] if compra else None,
    }
