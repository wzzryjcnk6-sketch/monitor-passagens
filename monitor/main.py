"""Uma rodada do monitor: busca preços, calcula notas, salva histórico, atualiza o painel e manda alertas.

Uso:
    python -m monitor.main                 # rodada normal
    python -m monitor.main --teste-email   # só manda um e-mail de teste de queda de preço
    python -m monitor.main --fonte exemplo # usa dados de mentira (para testar)
"""

import argparse
import importlib
import json
import os
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import alertas
from .nota import calcular_notas

RAIZ = Path(__file__).resolve().parent.parent
DOCS = RAIZ / "docs"
DADOS = RAIZ / "data"
BRASILIA = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019
HORARIOS = (12, 20)


def ler_json(caminho, padrao):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return padrao


def salvar_json(caminho, conteudo):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(conteudo, ensure_ascii=False, indent=1), encoding="utf-8")


def saida_actions(chave, valor):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"{chave}={valor}\n")


def url_painel():
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return None
    dono, nome = repo.split("/")
    return f"https://{dono.lower()}.github.io/{nome}/"


def proxima_atualizacao(agora):
    for dias in range(3):
        for h in HORARIOS:
            dia = (agora + timedelta(days=dias)).date()
            candidato = datetime(dia.year, dia.month, dia.day, h, tzinfo=BRASILIA)
            if candidato > agora + timedelta(minutes=15):
                return candidato
    return None


def motivo_para_parar(cfg, hoje):
    if cfg["controle"].get("ja_comprei"):
        return "Você marcou que já comprou a ida."
    if hoje > date.fromisoformat(cfg["controle"]["data_fim"]):
        return f"O período de monitoramento terminou em {cfg['controle']['data_fim']}."
    return None


def resumo_precos(opcoes):
    por_data = {}
    for o in opcoes:
        atual = por_data.get(o["data"])
        por_data[o["data"]] = o["preco_total"] if atual is None else min(atual, o["preco_total"])
    return {"menor_geral": min(por_data.values()) if por_data else None, "menor_por_data": por_data}


def teste_email(cfg):
    opcoes = ler_json(DOCS / "dados.json", {}).get("opcoes") or calcular_notas(
        importlib.import_module(".fonte_exemplo", __package__).buscar_ida(cfg), cfg)
    melhor = min(opcoes, key=lambda o: o["preco_total"])
    ok = alertas.queda_de_preco(melhor["preco_total"] + 312.40, melhor, melhor["preco_total"], url_painel(), teste=True)
    if not ok:
        raise SystemExit("E-mail de teste NÃO enviado: confira os secrets EMAIL_REMETENTE e EMAIL_SENHA_APP.")


def rodada(cfg, fonte_nome, forcar=False):
    agora = datetime.now(BRASILIA)
    dados_antigos = ler_json(DOCS / "dados.json", {})
    estado = ler_json(DADOS / "estado.json", {"falhas_seguidas": 0, "havia_opcao_no_orcamento": False})
    historico = ler_json(DOCS / "historico.json", [])
    painel = url_painel()

    parar = None if forcar else motivo_para_parar(cfg, agora.date())
    if parar:
        print(f"Monitor parado: {parar}")
        saida_actions("parado", "true")
        if dados_antigos.get("status", {}).get("parado") != parar:
            dados_antigos["status"] = {"ok": True, "parado": parar, "mensagem": f"Monitor encerrado. {parar}"}
            dados_antigos["proxima_atualizacao"] = None
            salvar_json(DOCS / "dados.json", dados_antigos)
        return

    base = {
        "viagem": cfg["viagem"],
        "fonte": fonte_nome,
        "atualizado_em": agora.isoformat(timespec="minutes"),
        "proxima_atualizacao": (p.isoformat(timespec="minutes") if (p := proxima_atualizacao(agora)) else None),
        "pesos": cfg["nota"],
    }

    try:
        fonte = importlib.import_module(f".fonte_{fonte_nome}", __package__)
        opcoes = fonte.buscar_ida(cfg)
        if not opcoes:
            raise RuntimeError("A busca não trouxe nenhuma opção de voo.")
    except Exception as erro:
        estado["falhas_seguidas"] = estado.get("falhas_seguidas", 0) + 1
        estado["ultimo_erro"] = str(erro)[:1000]
        print(f"FALHA ({estado['falhas_seguidas']}ª seguida): {erro}")
        if estado["falhas_seguidas"] == 2:
            alertas.falha_repetida(erro, painel)
        salvar_json(DADOS / "estado.json", estado)
        dados_antigos.update({k: base[k] for k in ("atualizado_em", "proxima_atualizacao")})
        dados_antigos["status"] = {"ok": False, "mensagem": f"Falha na última busca: {str(erro)[:300]}",
                                   "falhas_seguidas": estado["falhas_seguidas"]}
        salvar_json(DOCS / "dados.json", dados_antigos)
        return

    calcular_notas(opcoes, cfg)
    opcoes.sort(key=lambda o: -o["nota"])
    resumo = resumo_precos(opcoes)
    menor_antes = historico[-1]["menor_geral"] if historico else None
    menor_ja_visto = min([h["menor_geral"] for h in historico] + [resumo["menor_geral"]])

    historico.append({"quando": base["atualizado_em"], **resumo})
    salvar_json(DOCS / "historico.json", historico)
    salvar_json(DADOS / "rodadas" / f"{agora:%Y-%m-%dT%H-%M}.json", opcoes)
    salvar_json(DOCS / "dados.json", {
        **base,
        "status": {"ok": True, "mensagem": "Busca concluída."},
        "resumo": {**resumo, "menor_anterior": menor_antes, "menor_ja_visto": menor_ja_visto},
        "opcoes": opcoes,
    })
    print(f"{len(opcoes)} opções; menor preço R$ {resumo['menor_geral']:.2f} (antes: {menor_antes})")

    # Alertas: só quando algo mudou de verdade.
    melhor = min(opcoes, key=lambda o: o["preco_total"])
    if menor_antes is not None and menor_antes - resumo["menor_geral"] >= cfg["alertas"]["queda_minima"]:
        alertas.queda_de_preco(menor_antes, melhor, menor_ja_visto, painel)
    dentro = melhor["preco_total"] <= cfg["viagem"]["orcamento_total"]
    if dentro and not estado.get("havia_opcao_no_orcamento") and historico[:-1]:
        alertas.entrou_no_orcamento(melhor, cfg["viagem"]["orcamento_total"], painel)

    estado.update({"falhas_seguidas": 0, "ultimo_erro": None, "havia_opcao_no_orcamento": dentro})
    salvar_json(DADOS / "estado.json", estado)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fonte", help="sobrescreve busca.fonte do config.toml")
    p.add_argument("--teste-email", action="store_true")
    p.add_argument("--forcar", action="store_true", help="roda mesmo depois da data de fim")
    args = p.parse_args()

    cfg = tomllib.loads((RAIZ / "config.toml").read_text(encoding="utf-8"))
    if args.teste_email:
        teste_email(cfg)
    else:
        rodada(cfg, args.fonte or cfg["busca"]["fonte"], args.forcar)


if __name__ == "__main__":
    main()
