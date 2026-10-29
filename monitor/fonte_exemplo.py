"""Fonte de dados de MENTIRA, só para testar o painel e os alertas sem gastar créditos."""

import random

# (companhias, voos, trechos [de, para, partida, chegada], duração, mala, preço base total)
MODELOS = [
    (["United"], ["UA 846", "UA 1580"], [("GRU", "IAH", "22:10", "05:45+1"), ("IAH", "PDX", "08:15+1", "10:45+1")], 1000, 1, 6100),
    (["LATAM", "Delta"], ["LA 8180", "DL 1422"], [("GRU", "JFK", "23:55", "07:40+1"), ("JFK", "PDX", "09:30+1", "13:05+1")], 1030, 1, 5650),
    (["American"], ["AA 906", "AA 2418"], [("GRU", "DFW", "21:40", "05:10+1"), ("DFW", "PDX", "06:15+1", "08:30+1")], 830, 1, 6900),
    (["Copa"], ["CM 702", "CM 412", "AS 1188"], [("GRU", "PTY", "06:25", "11:00"), ("PTY", "LAX", "13:45", "18:30"), ("LAX", "PDX", "20:15", "22:30")], 1085, 0, 4990),
    (["Delta"], ["DL 104", "DL 2741"], [("GRU", "ATL", "22:30", "06:30+1"), ("ATL", "PDX", "07:20+1", "09:40+1")], 790, 1, 7300),
    (["Avianca", "Alaska"], ["AV 86", "AV 244", "AS 541"], [("GRU", "BOG", "01:15", "05:45"), ("BOG", "SFO", "11:00", "17:20"), ("OAK", "PDX", "21:30", "23:20")], 1325, None, 4700),
]


def _hora(data, hhmm):
    from datetime import date, timedelta

    dia = date.fromisoformat(data)
    if "+1" in hhmm:
        dia += timedelta(days=1)
        hhmm = hhmm.replace("+1", "")
    return f"{dia.isoformat()}T{hhmm}"


def buscar_ida(cfg):
    adultos = cfg["viagem"]["adultos"]
    opcoes = []
    for i, data in enumerate(cfg["viagem"]["datas"]):
        for companhias, voos, pernas, duracao, mala, base in MODELOS:
            preco = round(base * random.uniform(0.92, 1.08) + i * 120, 2)
            trechos = [
                {"voo": voos[k], "companhia": companhias[min(k, len(companhias) - 1)], "de": a, "para": b,
                 "partida": _hora(data, p), "chegada": _hora(data, c)}
                for k, (a, b, p, c) in enumerate(pernas)
            ]
            escalas = [
                {"aeroporto": trechos[k]["para"], "cidade": None,
                 "duracao_min": _minutos_entre(trechos[k]["chegada"], trechos[k + 1]["partida"]),
                 "troca_aeroporto": trechos[k]["para"] != trechos[k + 1]["de"]}
                for k in range(len(trechos) - 1)
            ]
            opcoes.append({
                "id": f"{data}|{'-'.join(v.replace(' ', '') for v in voos)}",
                "data": data,
                "companhias": companhias,
                "voos": voos,
                "partida": trechos[0]["partida"],
                "chegada": trechos[-1]["chegada"],
                "duracao_min": duracao,
                "conexoes": len(escalas),
                "escalas": escalas,
                "trechos": trechos,
                "mala_de_mao": {1: "sim", 0: "nao", None: "verificar"}[mala],
                "preco_total": preco,
                "preco_pessoa": round(preco / adultos, 2),
                "link": f"https://www.google.com/travel/flights?q=Flights%20to%20PDX%20from%20GRU%20on%20{data}%20oneway",
                "link_tipo": "google",
                "vendedor": None,
            })
    return opcoes


def _minutos_entre(a, b):
    from datetime import datetime

    return int((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() // 60)
