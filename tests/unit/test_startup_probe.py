from tools.android.startup_probe import startup_healthy, warning_button


def _dialog(message: str, button: str = "Continue", package: str = "com.siva.project.x2") -> str:
    return (
        f'<hierarchy><node text="{message}"/>'
        f'<node package="{package}" resource-id="android:id/button1" '
        f'text="{button}" bounds="[100,200][300,400]"/></hierarchy>'
    )


def test_acknowledge_only_known_hardware_warning() -> None:
    assert warning_button(_dialog(
        "Your device does not match the hardware requirements of this application."
    )) == (200, 300)


def test_do_not_acknowledge_unrelated_dialog() -> None:
    assert warning_button(_dialog("Delete saved game data?")) is None
    assert warning_button(_dialog(
        "Your device does not match the hardware requirements", button="Cancel"
    )) is None
    assert warning_button(_dialog(
        "Your device does not match the hardware requirements", package="another.app"
    )) is None


def test_http_contact_does_not_hide_client_failure() -> None:
    assert not startup_healthy({"bootstrap_reached": True})
    healthy = {"bootstrap_reached": True, "awake": True, "main_process_alive": True}
    assert startup_healthy(healthy)
    for flag in ("memory_16gb_error", "shader_platform_error", "error"):
        assert not startup_healthy({**healthy, flag: True})
    assert not startup_healthy({**healthy, "main_process_alive": False})
