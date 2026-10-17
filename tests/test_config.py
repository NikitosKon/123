from app.config import Settings


def test_admin_ids_support_user_and_group_ids():
    settings = Settings(admin_ids="12345, -1009876543210, invalid")
    assert settings.admin_id_list == [12345, -1009876543210]


def test_notification_mode_is_validated():
    assert Settings(notification_mode="link").notification_mode == "link"
    assert Settings(notification_mode="card").notification_mode == "card"
