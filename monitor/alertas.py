"""Alertas por e-mail (Gmail com senha de app). Endereços e senha vêm só dos GitHub Secrets."""

import html
import os
import smtplib
from email.message import EmailMessage


def _brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _data_br(iso):
    return f"{iso[8:10]}/{iso[5:7]}" if iso else "?"


def _botao(url, texto):
    return (f'<a href="{html.escape(url)}" style="display:inline-block;background:#1a56db;color:#fff;'
            f'padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:600">{html.escape(texto)}</a>')


def _resumo_opcao(o):
    escalas = ", ".join(e["aeroporto"] or "?" for e in o["escalas"]) or "direto"
    return (f"<p style='margin:4px 0'><b>{html.escape(' + '.join(o['companhias']))}</b> · "
            f"partida {_data_br(o['data'])} às {o['partida'][11:16]} · {o['conexoes']} conexão(ões) ({escalas})<br>"
            f"{_brl(o['preco_total'])} no total · {_brl(o['preco_pessoa'])} por pessoa</p>")


def _envolver(titulo, corpo, url_painel):
    rodape = f"<p style='margin-top:24px'>{_botao(url_painel, 'Abrir o painel')}</p>" if url_painel else ""
    return (f"<div style='font-family:Arial,sans-serif;max-width:560px;color:#111'>"
            f"<h2 style='margin:0 0 12px'>{html.escape(titulo)}</h2>{corpo}{rodape}"
            f"<p style='color:#888;font-size:12px;margin-top:24px'>Monitor de passagens GRU → PDX</p></div>")


def enviar(assunto, corpo_html):
    remetente = os.environ.get("EMAIL_REMETENTE")
    senha = os.environ.get("EMAIL_SENHA_APP")
    destino = os.environ.get("EMAIL_DESTINO") or remetente
    if not (remetente and senha):
        print(f"(e-mail não configurado; alerta não enviado: {assunto})")
        return False
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = remetente
    msg["To"] = destino
    msg.set_content("Abra este e-mail num leitor que mostre HTML.")
    msg.add_alternative(corpo_html, subtype="html")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(remetente, senha.replace(" ", ""))
            s.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        print(f"ERRO ao enviar e-mail ({assunto}): {e}")
        return False
    print(f"E-mail enviado: {assunto}")
    return True


def queda_de_preco(anterior, melhor, menor_ja_visto, url_painel, teste=False):
    novo = melhor["preco_total"]
    prefixo = "[TESTE] " if teste else ""
    assunto = f"{prefixo}⬇ Ida GRU→PDX baixou para {_brl(novo)}"
    corpo = (
        f"<p>Preço anterior: <s>{_brl(anterior)}</s><br>"
        f"<b style='font-size:20px'>Preço novo: {_brl(novo)}</b> ({_brl(melhor['preco_pessoa'])} por pessoa)<br>"
        f"Menor preço já visto: {_brl(menor_ja_visto)}</p>"
        f"{_resumo_opcao(melhor)}"
        f"<p style='margin-top:16px'>{_botao(melhor['link'], 'Ver e comprar esta opção')}</p>"
    )
    if teste:
        corpo = "<p style='color:#b45309'><b>Este é um e-mail de teste.</b> Se chegou, os alertas estão funcionando.</p>" + corpo
    return enviar(assunto, _envolver("A ida ficou mais barata", corpo, url_painel))


def entrou_no_orcamento(melhor, orcamento, url_painel):
    assunto = f"✅ Ida GRU→PDX dentro do orçamento: {_brl(melhor['preco_total'])}"
    corpo = (f"<p>Apareceu uma opção abaixo de {_brl(orcamento)} para as 2 pessoas.</p>{_resumo_opcao(melhor)}"
             f"<p style='margin-top:16px'>{_botao(melhor['link'], 'Ver e comprar esta opção')}</p>")
    return enviar(assunto, _envolver("Opção dentro do orçamento", corpo, url_painel))


def falha_repetida(erro, url_painel):
    assunto = "⚠ Monitor de passagens: 2 rodadas seguidas sem conseguir buscar preços"
    corpo = (f"<p>As duas últimas tentativas de buscar preços falharam. Os dados do painel podem estar desatualizados.</p>"
             f"<p style='background:#f3f4f6;padding:8px;font-family:monospace;font-size:12px'>{html.escape(str(erro))[:800]}</p>"
             f"<p>Causas comuns: créditos da Apify acabaram no mês, chave (APIFY_TOKEN) errada ou o robô mudou.</p>")
    return enviar(assunto, _envolver("O monitor está com problema", corpo, url_painel))
