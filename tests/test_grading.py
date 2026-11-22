from services.granite import _keyword_grade


def test_completely_wrong_answer_gets_zero():
    question = {
        "text": "What is an API?",
        "key_points": ["Application Programming Interface", "Communication between software"]

    }

    result = _keyword_grade(question, "Banana is a yellow fruit.")

    assert result["score"] == 0
    assert result["verdict"] == "incorrect"


def test_irrelevant_answer_gets_zero():
    question = {
        "text": "What is a database?",
        "key_points": ["Organized data", "Storage and retrieval"]
    }

    result = _keyword_grade(question, "I like playing cricket every day.")

    assert result["score"] == 0
    assert result["verdict"] == "incorrect"



def test_false_definition_does_not_get_partial_marks():
    question = {
        "text": "What is an API?",
        "key_points": [
            "Application Programming Interface",
            "Communication between software"
        ]
    }

    result = _keyword_grade(
        question,
        "API means application programming interface for eating bananas."
    )

    assert result["verdict"] == "incorrect"
    assert result["score"] == 0
