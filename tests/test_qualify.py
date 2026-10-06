"""Qualification sans API : forme sociale, dénomination, date, nature."""
import pytest

import qualify

PV = """Hélianthe Technologies
SAS au capital de 50 000 euros
Siège social : 24 rue des Tanneurs, 69007 Lyon
Procès-verbal d'Assemblée Générale Extraordinaire du 15 mars 2023
Le 15 mars 2023, les associés se sont réunis…"""


def test_qualify_pv():
    q = qualify.qualify(PV)
    assert q == {"forme": "SAS", "societe": "Hélianthe Technologies", "date": "2023-03-15", "nature": "AGE"}


@pytest.mark.parametrize("text,forme", [
    ("NOVATECH SASU au capital de 1 euro", "SASU"),
    ("Société par actions simplifiée unipersonnelle", "SASU"),
    ("ACME Société anonyme à conseil d'administration", "SA"),
    ("DUPONT SARL, gérant", "SARL"),
    ("GAEC RECONNU ASSERAY PERE ET FILS\nSociété civile au capital social variable", "GAEC"),
    ("Société civile au capital de 1 000 euros", "SC"),
    ("Rien de reconnaissable", ""),
])
def test_forme_sociale(text, forme):
    assert qualify.forme_sociale(text) == forme


def test_date_variants():
    assert qualify.date_acte("Décision du Président en date du 1er juillet 2026") == "2026-07-01"
    assert qualify.date_acte("Assemblée du 02/11/2020") == "2020-11-02"
    assert qualify.date_acte("pas de date", "ASSERAY - Actes du 07-02-2023.pdf") == "2023-02-07"
    assert qualify.date_acte("rien", "sans_date.pdf") == ""


def test_nature():
    assert qualify.nature("PROCÈS-VERBAL DE L'ASSEMBLÉE GÉNÉRALE ORDINAIRE ANNUELLE") == "AGO"
    assert qualify.nature("Décisions du Président") == "DECISION"
    assert qualify.nature("Assemblée des associés") == "AG"
