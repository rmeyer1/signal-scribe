from signal_scribe.embeddings import vector_to_sql


def test_vector_to_sql_formats_pgvector_literal():
    assert vector_to_sql([0.1, -0.25, 1.234567891]) == "[0.1,-0.25,1.234567891]"
