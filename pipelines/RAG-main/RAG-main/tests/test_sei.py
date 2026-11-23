"""Testes unitários das regras de interpretação do SEI (sem PDFs)."""

from app.ingestion import sei

# --------------------------------------------------------------------------
# Rodapé
# --------------------------------------------------------------------------


def test_rodape_com_parenteses():
    texto = "corpo\nMemorando 131 (142739020)         SEI 04030-00001001/2024-23 / pg. 38\n"
    r = sei.extrair_rodape(texto)
    assert r == sei.Rodape("Memorando 131", "142739020", "04030-00001001/2024-23", 38)


def test_rodape_sem_parenteses():
    texto = "Despacho 140494121         SEI 04030-00001001/2024-23 / pg. 36\n"
    r = sei.extrair_rodape(texto)
    assert r.rotulo == "Despacho"
    assert r.documento_sei_id == "140494121"
    assert r.pagina == 36


def test_rodape_rotulo_composto():
    texto = "Despacho CONSEPE (213940949)         SEI 04030-00001179/2025-55 / pg. 183"
    r = sei.extrair_rodape(texto)
    assert r.rotulo == "Despacho CONSEPE"
    assert r.documento_sei_id == "213940949"


def test_rodape_usa_ultima_ocorrencia():
    texto = (
        "citação: Projeto (140362209) SEI 04030-00001001/2024-23 / pg. 9\n"
        "texto\n"
        "Memorando 6 (194797531)  SEI 04030-00001001/2024-23 / pg. 57\n"
    )
    assert sei.extrair_rodape(texto).documento_sei_id == "194797531"


def test_pagina_sem_rodape():
    assert (
        sei.extrair_rodape("Governo do Distrito Federal\nMemorando Nº 98/2024 - UNDF/REIT") is None
    )


# --------------------------------------------------------------------------
# Tipo e número do documento
# --------------------------------------------------------------------------


def test_tipo_do_rotulo():
    assert sei.tipo_do_rotulo("Memorando 131") == "Memorando"
    assert sei.tipo_do_rotulo("Termo de Aceite 19") == "Termo de Aceite"
    assert sei.tipo_do_rotulo("Despacho CONSEPE") == "Despacho"
    assert sei.tipo_do_rotulo("Regimento Interno V3") == "Regimento Interno"
    assert sei.tipo_do_rotulo("Nota Jurídica 115") == "Nota Jurídica"
    assert sei.tipo_do_rotulo("Circular 3") == "Circular"


CABECALHO_MEMORANDO = (
    "Governo do Distrito Federal\nUniversidade do Distrito Federal\nReitoria\n"
    "Centros Interdisciplinares\n \nMemorando Nº 98/2024 - UNDF/REIT/CEINTER\n"
    "Brasília-DF, 07 de maio de 2024.\n"
)


def test_numero_memorando():
    assert (
        sei.extrair_numero_documento(CABECALHO_MEMORANDO, "Memorando 98")
        == "98/2024 - UNDF/REIT/CEINTER"
    )


def test_numero_nota_juridica_com_n_ponto():
    texto = "Procuradoria Jurídica\nNota Jurídica N.º 115/2025 - UNDF/REIT/PROJUR\nBrasília-DF"
    assert sei.extrair_numero_documento(texto, "Nota Jurídica 115") == "115/2025 - UNDF/REIT/PROJUR"


def test_numero_sigla_com_hifen():
    texto = "Vice-Reitoria\nOfício Nº 20/2026 - UNDF/REIT/VICE-REIT/CEINTER\nBrasília-DF"
    assert (
        sei.extrair_numero_documento(texto, "Ofício 20") == "20/2026 - UNDF/REIT/VICE-REIT/CEINTER"
    )


def test_numero_quebrado_em_duas_linhas():
    texto = "Centros Interdisciplinares\n \n \nTERMO DE ACEITE\n19/2026\nTERMO DE ANUÊNCIA"
    assert sei.extrair_numero_documento(texto, "Termo de Aceite 19") == "19/2026"


def test_edital_aceita_chamada_publica():
    texto = "Gabinete\nChamada Pública n.º 53/2024 - FAPDF/PRES/GAB\nBrasília-DF"
    assert sei.extrair_numero_documento(texto, "Edital") == "53/2024 - FAPDF/PRES/GAB"


def test_numero_de_outro_tipo_e_ignorado():
    # Despacho que responde ao Memorando 131: o número é do memorando, não do despacho.
    texto = (
        "Reitoria\nDespacho - UNDF/REIT\n"
        "Assunto: resposta ao Memorando Nº 131/2024 - UNDF/REIT/CEINTER\n"
    )
    assert sei.extrair_numero_documento(texto, "Despacho") is None


def test_numero_citado_no_corpo_e_ignorado():
    # Armadilha real: Termo de Outorga 500/2024 citado num despacho do CONSEPE.
    corpo = "\n".join(f"linha {i}" for i in range(sei.LINHAS_CABECALHO))
    texto = "Despacho - CONSEPE\n" + corpo + "\nDespacho nº 500/2024 - FAPDF/SUCTI/COOTI\n"
    assert sei.extrair_numero_documento(texto, "Despacho CONSEPE") is None


def test_numero_divergente_do_rotulo_e_descartado():
    texto = "Memorando Nº 22/2024 - UNDF/REIT/CEINTER/COETI"
    assert sei.extrair_numero_documento(texto, "Memorando 11") is None


def test_tipo_sem_numeracao_oficial():
    texto = "PROPOSTA EDITAL 06/2024 PROGRAMA FAPDF LEARNING"
    assert sei.extrair_numero_documento(texto, "Projeto") is None


def test_processo_do_nome_arquivo():
    assert (
        sei.processo_do_nome_arquivo("SEI_04030_00001001_2024_23 (2).pdf")
        == "04030-00001001/2024-23"
    )
    assert sei.processo_do_nome_arquivo("qualquer.pdf") is None


# --------------------------------------------------------------------------
# Limpeza
# --------------------------------------------------------------------------


def test_ligaduras_normalizadas():
    assert sei.limpar_texto("cientiﬁca, ﬂuxo").texto == "cientifica, fluxo"


def test_reparo_de_glifos_por_documento():
    r = sei.limpar_texto("Incen\x01var a pesquisa cien\x02ﬁca", "140334392")
    assert r.texto == "Incentivar a pesquisa científica"
    assert r.glifos_reparados == 2
    assert r.glifos_desconhecidos == 0


def test_glifo_sem_reparo_e_removido_e_contado():
    r = sei.limpar_texto("Incen\x01var", "999")
    assert r.texto == "Incenvar"
    assert r.glifos_desconhecidos == 1


def test_remove_moldura_sei_e_mantem_assinatura():
    texto = (
        "Atenciosamente,\n"
        "Documento assinado eletronicamente por FULANO DE TAL - Matr.123, em 06/06/2024.\n"
        "A autenticidade do documento pode ser conferida no site:\n"
        "https://sei.df.gov.br/sei/controlador_externo.php?\n"
        "acao=documento_conferir&id_orgao_acesso_externo=0 \n"
        "Código Verificador: 142739020 Código CRC: CABB585A.\n"
        '"Brasília - Patrimônio Cultural da Humanidade"\n'
        "Edifício Governança Bloco B 2º Andar - Bairro Granja do Torto - CEP 70.636-000 - DF\n"
        "Telefone(s): 34628866\n"
        "Sítio  - https://undf.edu.br/\n"
        "04030-00001001/2024-23\n"
        "Doc. SEI/GDF 142739020\n"
        "Memorando 131 (142739020)         SEI 04030-00001001/2024-23 / pg. 38\n"
    )
    limpo = sei.limpar_texto(texto).texto
    assert limpo == (
        "Atenciosamente,\n"
        "Documento assinado eletronicamente por FULANO DE TAL - Matr.123, em 06/06/2024."
    )


def test_substituicoes_de_caracteres():
    assert sei.limpar_texto("​Despacho ̶ UNDF\n item").texto == "Despacho - UNDF\n• item"


def test_numero_do_rotulo_ignora_datas():
    assert sei.numero_do_rotulo("Memorando 131") == "131"
    assert sei.numero_do_rotulo("Decreto n. 44.969, de 19/09/2023") is None
    assert sei.numero_do_rotulo("Regimento Interno V3") is None


# --------------------------------------------------------------------------
# Metadados (RAG-02): assunto, data e unidade
# --------------------------------------------------------------------------


def test_assunto_em_uma_linha():
    texto = (
        "Memorando Nº 1/2024 - UNDF/REIT\nAssunto: Pedido de anuência para edital FAP\n1.\nTexto"
    )
    assert sei.extrair_assunto(texto) == "Pedido de anuência para edital FAP"


def test_assunto_quebrado_com_parenteses():
    texto = (
        "Assunto: Proposta de criação do Núcleo de Inteligência Artificial da Universidade\n"
        "(NIAUnDF). Manifestação da COCBS.\n"
        "Senhora Coordenadora,\n"
    )
    assert sei.extrair_assunto(texto) == (
        "Proposta de criação do Núcleo de Inteligência Artificial da Universidade "
        "(NIAUnDF). Manifestação da COCBS."
    )


def test_assunto_com_aspas_abertas_continua():
    texto = (
        'Assunto: Esclarecimentos sobre o documento "Justificativa de Mudança do Pro\n'
        'jeto e Foco Principal: Do CIIA GovTech para o NIAUnDF"\n'
        "Senhora Reitora,\n"
    )
    assert sei.extrair_assunto(texto).endswith('para o NIAUnDF"')


def test_assunto_termina_em_conectivo_continua():
    texto = (
        "Assunto: Requer encaminhamento às Pró-Reitorias de Pesquisa e\n"
        "Pós-Graduação e de Extensão, com prazo.\n"
        "1.\n"
    )
    assert sei.extrair_assunto(texto) == (
        "Requer encaminhamento às Pró-Reitorias de Pesquisa e "
        "Pós-Graduação e de Extensão, com prazo."
    )


def test_assunto_nao_engole_saudacao_nem_paragrafo():
    assert sei.extrair_assunto("Assunto: criação de núcleo na UnDF\nPrezado,\nTexto") == (
        "criação de núcleo na UnDF"
    )
    assert sei.extrair_assunto("Assunto: Pedido de anuência\nSolicito termo de anuência") == (
        "Pedido de anuência"
    )


def test_assunto_palavra_solta_no_fim():
    assert sei.extrair_assunto("Assunto: Proposta da Universidade\nNIAUnDF\n1.") == (
        "Proposta da Universidade NIAUnDF"
    )


def test_sem_assunto():
    assert sei.extrair_assunto("TERMO DE ACEITE\n19/2026\nTexto sem assunto") is None


def test_data_do_cabecalho():
    assert sei.extrair_data("Memorando\nBrasília-DF, 07 de maio de 2024.\n") == "2024-05-07"
    assert sei.extrair_data("Despacho\nBrasília, 09 de março de 2024.") == "2024-03-09"
    assert sei.extrair_data("GT de IA\nBrasília 31 de maio de 2024") == "2024-05-31"


def test_data_invalida_ou_ausente():
    assert sei.extrair_data("Brasília-DF, 07 de maiô de 2024.") is None
    assert sei.extrair_data("Texto sem data") is None


def test_data_assinatura_mais_antiga():
    texto = (
        "Documento assinado eletronicamente por FULANO DE TAL - Matr.123,\n"
        "Professor, em 12/02/2026, às 10:37, conforme art. 6º\n"
        "Documento assinado eletronicamente por CICLANA - Matr.456, em 10/02/2026, às 09:00\n"
    )
    assert sei.extrair_data_assinatura(texto) == "2026-02-10"
    assert sei.extrair_data_assinatura("sem assinatura") is None


def test_unidade_pelo_numero():
    assert sei.extrair_unidade("", "98/2024 - UNDF/REIT/CEINTER") == "UNDF/REIT/CEINTER"


def test_unidade_pelo_cabecalho_de_despacho():
    # O SEI escreve "Despacho ̶ UNDF/REIT" com um traço combinante (U+0336).
    assert sei.extrair_unidade("Reitoria\nDespacho  \u0336  UNDF/REIT\n", None) == "UNDF/REIT"
    texto = "Vice-Reitoria\nDespacho - UNDF/VICE-REIT/CEINTER/COETI\n"
    assert sei.extrair_unidade(texto, None) == "UNDF/VICE-REIT/CEINTER/COETI"


def test_unidade_ausente():
    assert sei.extrair_unidade("TERMO DE ACEITE\n5/2024\n", "5/2024") is None
