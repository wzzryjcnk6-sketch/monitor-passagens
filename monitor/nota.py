"""Nota de "Melhor oferta" (0 a 100). Pesos e penalidades vêm do config.toml."""


def _normalizado(valor, minimo, maximo):
    """1 = melhor (menor valor), 0 = pior."""
    if valor is None:
        return 0.5
    if maximo == minimo:
        return 1.0
    return (maximo - valor) / (maximo - minimo)


def _brl(v):
    return f"R$ {v:,.0f}".replace(",", ".")


def _horas(m):
    return f"{m // 60}h{m % 60:02d}"


def calcular_notas(opcoes, cfg):
    pesos = cfg["nota"]["pesos"]
    pen = cfg["nota"]["penalidades"]
    lim = cfg["nota"]["limites"]
    orcamento = cfg["viagem"]["orcamento_total"]

    precos = [o["preco_total"] for o in opcoes]
    duracoes = [o["duracao_min"] for o in opcoes if o["duracao_min"] is not None]
    max_conexoes = max([o["conexoes"] for o in opcoes] + [2])
    soma_pesos = sum(pesos.values()) or 1

    for o in opcoes:
        partes = {
            "preco": _normalizado(o["preco_total"], min(precos), max(precos)),
            "duracao": _normalizado(o["duracao_min"], min(duracoes, default=0), max(duracoes, default=0)),
            "conexoes": 1 - o["conexoes"] / max_conexoes,
            "mala_de_mao": {"sim": 1.0, "nao": 0.0}.get(o["mala_de_mao"], 0.5),
        }
        base = sum(pesos[k] * partes[k] for k in pesos) / soma_pesos * 100

        motivos = [
            f"Preço {_brl(o['preco_total'])}: {round(partes['preco'] * 100)}% do melhor possível entre as opções",
        ]
        if o["duracao_min"] is not None:
            motivos.append(f"Viagem de {_horas(o['duracao_min'])}: {round(partes['duracao'] * 100)}% do melhor")
        motivos.append({0: "Voo direto", 1: "1 conexão"}.get(o["conexoes"], f"{o['conexoes']} conexões"))
        motivos.append({"sim": "Mala de mão incluída", "nao": "Sem mala de mão",
                        "verificar": "Mala de mão: verificar"}[o["mala_de_mao"]])

        desconto = 0
        for e in o["escalas"]:
            d = e["duracao_min"]
            if d is not None and d < lim["conexao_curta_min"]:
                desconto += pen["conexao_curta"]
                motivos.append(f"−{pen['conexao_curta']}: conexão curta em {e['aeroporto']} ({_horas(d)})")
            if d is not None and d > lim["conexao_longa_min"]:
                desconto += pen["conexao_longa"]
                motivos.append(f"−{pen['conexao_longa']}: conexão longa em {e['aeroporto']} ({_horas(d)})")
            if e["troca_aeroporto"]:
                desconto += pen["troca_de_aeroporto"]
                motivos.append(f"−{pen['troca_de_aeroporto']}: troca de aeroporto em {e['aeroporto']}")
        o["acima_orcamento"] = o["preco_total"] > orcamento
        if o["acima_orcamento"]:
            desconto += pen["acima_do_orcamento"]
            motivos.append(f"−{pen['acima_do_orcamento']}: acima do orçamento de {_brl(orcamento)}")

        o["nota"] = max(0, min(100, round(base - desconto)))
        o["nota_motivos"] = motivos
    return opcoes
