from app.offerings.sync_service import _combined_offering_content


def test_uses_payload_content_as_entire_offering_text():
    text = _combined_offering_content(
        {"content": "Description\n\n## pitch.txt\nDeck body"},
        [{"file_name": "ignored.pdf", "content": "should not replace payload"}],
        "ignored description",
    )
    assert text == "Description\n\n## pitch.txt\nDeck body"


def test_builds_description_plus_every_doc():
    text = _combined_offering_content(
        {},
        [
            {"file_name": "pitch.txt", "content": "Deck body"},
            {"file_name": "empty.txt", "content": ""},
            {"file_name": "pricing.docx", "content": "Price list"},
        ],
        "Folder description",
    )
    assert text.startswith("Folder description")
    assert "## pitch.txt\nDeck body" in text
    assert "## pricing.docx\nPrice list" in text
    assert "empty.txt" not in text


def test_falls_back_to_description_when_docs_have_no_text():
    text = _combined_offering_content(
        {"content": None},
        [{"file_name": "deck.pptx", "content": ""}],
        "Folder-only description",
    )
    assert text == "Folder-only description"
