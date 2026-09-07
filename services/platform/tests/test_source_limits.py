from alos.sources.registry import _chunk_content


def test_long_source_lines_are_split_into_unique_bounded_citations() -> None:
    content = "x" * 95

    chunks = _chunk_content("LONG_SOURCE", "v1", content, max_chars=32)

    assert len(chunks) == 3
    assert all(len(chunk[3]) <= 32 for chunk in chunks)
    assert len({chunk[1] for chunk in chunks}) == len(chunks)
    assert "".join(chunk[3] for chunk in chunks) == content
