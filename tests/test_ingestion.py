from ingestion.config import config
from ingestion.download import _is_same


def test_configuration_lue_depuis_l_environnement():
    assert config.years == ["2024", "2025"]
    assert config.departments == ["75", "77", "78", "91", "92", "93", "94", "95"]
    assert config.raw_table_fqn == "projet-test.raw.dvf_mutations"


def test_url_geo_dvf():
    assert config.file_url("2025", "75").endswith("/geo-dvf/latest/csv/2025/departements/75.csv.gz")


def test_fichier_inchange_si_metadonnees_identiques():
    meta = {"last_modified": "Sat, 12 Oct 2026 08:00:00 GMT", "content_length": "123", "etag": "abc"}
    assert _is_same(meta, dict(meta))


def test_fichier_republie_si_une_metadonnee_change():
    local = {"last_modified": "Sat, 05 Apr 2026 08:00:00 GMT", "content_length": "123", "etag": "abc"}
    remote = {**local, "last_modified": "Sat, 12 Oct 2026 08:00:00 GMT"}
    assert not _is_same(local, remote)


def test_pas_de_cache_sans_metadonnees():
    remote = {"last_modified": None, "content_length": None, "etag": None}
    assert not _is_same(None, remote)
    # aucune métadonnée distante comparable : on retélécharge par prudence
    assert not _is_same({"etag": "abc"}, remote)
