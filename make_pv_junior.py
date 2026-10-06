"""Génère le PV d'un junior pour la démo : AGE de levée de fonds où la suppression du DPS,
la délégation au Président et le détail des votes manquent (ce qui a été négocié à l'oral)."""
from pathlib import Path
import pymupdf

TEXT = """NOVATECH SAS
Société par actions simplifiée au capital de 100 000 euros
Siège social : 12 rue de l'Innovation, 75011 Paris
RCS Paris 912 345 678

PROCES-VERBAL DE L'ASSEMBLEE GENERALE EXTRAORDINAIRE DU 28 SEPTEMBRE 2026

L'an deux mille vingt-six, le vingt-huit septembre à dix heures, les associés de la société NOVATECH SAS se sont réunis en assemblée générale extraordinaire au siège social, sur convocation du Président adressée par courriel le 11 septembre 2026.

L'assemblée est présidée par Monsieur Marc Lefevre, Président. Madame Julie Bernard est désignée secrétaire.

La feuille de présence, certifiée exacte par le bureau, permet de constater que les associés présents ou représentés possèdent 100 000 actions sur les 100 000 actions ayant droit de vote. Le quorum étant atteint, l'assemblée peut valablement délibérer.

Ordre du jour :
- Augmentation de capital par émission d'actions nouvelles ;
- Modification corrélative des statuts ;
- Pouvoirs pour les formalités.

PREMIERE RESOLUTION
L'assemblée générale décide d'augmenter le capital social d'une somme de 200 000 euros par émission de 200 000 actions nouvelles d'une valeur nominale de 1 euro chacune, émises au prix de 50 euros, soit avec une prime d'émission de 49 euros par action.
Cette résolution est adoptée.

DEUXIEME RESOLUTION
L'assemblée générale décide de modifier en conséquence l'article 7 des statuts relatif au capital social.
Cette résolution est adoptée.

TROISIEME RESOLUTION
L'assemblée générale confère tous pouvoirs au porteur d'une copie ou d'un extrait du présent procès-verbal pour accomplir les formalités.
Cette résolution est adoptée.

L'ordre du jour étant épuisé, la séance est levée à onze heures.

Le Président                                   La Secrétaire
"""

out = Path(__file__).parent / "pv_junior_levee_de_fonds.pdf"
doc = pymupdf.open()
page = doc.new_page()
page.insert_textbox(pymupdf.Rect(60, 60, 540, 800), TEXT, fontsize=9.5)
doc.save(out)
print("écrit :", out)
