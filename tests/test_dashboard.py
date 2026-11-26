from streamlit.testing.v1 import AppTest
from app import _input_data


def _app():
    return AppTest.from_file("app.py").run(timeout=30)


def test_initial_screen_requires_consent():
    app = _app()
    assert not app.exception
    assert "Ready when you are" in app.markdown[3].value


def test_complete_and_degraded_demos_render_dashboard():
    app = _app()
    app.checkbox[0].set_value(True).run(timeout=30)
    assert not app.exception
    assert len(app.tabs) == 3
    assert "Synthetic demo" in app.markdown[3].value
    app.radio[0].set_value("Demo with missing data").run(timeout=30)
    assert not app.exception
    assert any("Withheld" in item.value for item in app.markdown)


def test_session_reset_returns_to_consent_screen():
    app = _app()
    app.checkbox[0].set_value(True).run(timeout=30)
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert "Ready when you are" in app.markdown[3].value


def test_invalid_upload_returns_a_clear_error_without_disk_io():
    class InvalidUpload:
        name = "bad.csv"

        @staticmethod
        def getvalue():
            return b"timestamp,steps\n2025-01-01 00:00,not-a-count\n"

    data, label, message = _input_data("Upload my CSV", InvalidUpload(), "Asia/Kolkata")
    assert data is None
    assert label == "Your CSV"
    assert "could not use" in message
