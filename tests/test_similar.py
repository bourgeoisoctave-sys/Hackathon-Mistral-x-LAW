"""Classement des cas similaires (pur, sans API)."""
import similar

INDEX = [
    {"source": "a.pdf", "type_operation": "AGE_levee_de_fonds", "nature": "AGE", "forme": "SAS", "brut": 80, "date": "2025-06-01", "societe": "A"},
    {"source": "b.pdf", "type_operation": "AGE_levee_de_fonds", "nature": "AGE", "forme": "SA", "brut": 95, "date": "2024-06-01", "societe": "B"},
    {"source": "c.pdf", "type_operation": "AGE_levee_de_fonds", "nature": "DECISION", "forme": "SAS", "brut": 40, "date": "2026-01-01", "societe": "C"},
    {"source": "d.pdf", "type_operation": "AGO_annuelle", "nature": "AGO", "forme": "SAS", "brut": 100, "date": "2026-03-01", "societe": "D"},
]
DRAFT = {"type_operation": "AGE_levee_de_fonds", "nature": "AGE", "forme": "SAS"}


def test_same_type_always_beats_other_types():
    top = similar.rank(DRAFT, INDEX, n=4)
    assert top[-1]["source"] == "d.pdf"  # seul d est d'un autre type, malgré brut 100 et date récente


def test_nature_and_forme_beat_raw_coverage_alone():
    top = similar.rank(DRAFT, INDEX, n=3)
    assert [t["source"] for t in top] == ["a.pdf", "b.pdf", "c.pdf"]
    assert "même forme sociale (SAS)" in top[0]["raisons"] and "même nature (AGE)" in top[0]["raisons"]
    assert "même forme sociale (SAS)" not in top[1]["raisons"]


def test_n_limits_and_reasons_present():
    top = similar.rank(DRAFT, INDEX, n=2)
    assert len(top) == 2 and all(t["raisons"] and t["points"] > 0 for t in top)


def test_missing_date_is_not_recent():
    idx = [{**INDEX[0], "date": ""}, {**INDEX[0], "source": "z.pdf", "date": "2026-01-01"}]
    assert similar.rank(DRAFT, idx, n=2)[0]["source"] == "z.pdf"


def test_merge_states_is_monotonic_for_untouched_clauses():
    import redraft
    avant = [{"id": "a", "etat": "presente"}, {"id": "b", "etat": "partielle"}, {"id": "c", "etat": "absente"}]
    apres = [{"id": "a", "etat": "partielle"}, {"id": "b", "etat": "presente"}, {"id": "c", "etat": "partielle"}]
    out = {c["id"]: c["etat"] for c in redraft.merge_states(avant, apres, modifiees={"c"})}
    assert out == {"a": "presente", "b": "presente", "c": "partielle"}  # a protégée, b améliorée, c re-vérifiée
    out2 = {c["id"]: c["etat"] for c in redraft.merge_states(avant, apres, modifiees={"a"})}
    assert out2["a"] == "partielle"  # modifiée : la re-vérification fait foi
