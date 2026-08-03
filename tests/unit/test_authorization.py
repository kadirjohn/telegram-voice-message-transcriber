from __future__ import annotations

from unittest.mock import patch

from app.db.enums import UserRole
from app.services.authorization import AuthorizationService


class TestAuthorizationService:
    @patch("app.services.authorization.UserRepository")
    def test_bootstrap_owner_creates_owner(self, mock_repo_class) -> None:
        mock_repo = mock_repo_class.return_value
        auth = AuthorizationService(user_repo=mock_repo)
        auth.bootstrap_owner()
        mock_repo.upsert.assert_called_once()

    @patch("app.services.authorization.UserRepository")
    def test_is_owner_returns_true_for_owner(self, mock_repo_class) -> None:
        mock_repo = mock_repo_class.return_value
        mock_user = type("User", (), {"role": UserRole.OWNER})()
        mock_repo.get_by_telegram_id.return_value = mock_user

        auth = AuthorizationService(user_repo=mock_repo)
        assert auth.is_owner(123) is True

    @patch("app.services.authorization.UserRepository")
    def test_is_owner_returns_false_for_user(self, mock_repo_class) -> None:
        mock_repo = mock_repo_class.return_value
        mock_user = type("User", (), {"role": UserRole.USER})()
        mock_repo.get_by_telegram_id.return_value = mock_user

        auth = AuthorizationService(user_repo=mock_repo)
        assert auth.is_owner(123) is False

    @patch("app.services.authorization.UserRepository")
    def test_is_admin_returns_true_for_admin(self, mock_repo_class) -> None:
        mock_repo = mock_repo_class.return_value
        mock_user = type("User", (), {"role": UserRole.ADMIN})()
        mock_repo.get_by_telegram_id.return_value = mock_user

        auth = AuthorizationService(user_repo=mock_repo)
        assert auth.is_admin(123) is True

    @patch("app.services.authorization.UserRepository")
    def test_is_admin_returns_true_for_owner(self, mock_repo_class) -> None:
        mock_repo = mock_repo_class.return_value
        mock_user = type("User", (), {"role": UserRole.OWNER})()
        mock_repo.get_by_telegram_id.return_value = mock_user

        auth = AuthorizationService(user_repo=mock_repo)
        assert auth.is_admin(123) is True

    @patch("app.services.authorization.UserRepository")
    def test_is_admin_returns_false_for_user(self, mock_repo_class) -> None:
        mock_repo = mock_repo_class.return_value
        mock_user = type("User", (), {"role": UserRole.USER})()
        mock_repo.get_by_telegram_id.return_value = mock_user

        auth = AuthorizationService(user_repo=mock_repo)
        assert auth.is_admin(123) is False

    @patch("app.services.authorization.UserRepository")
    def test_add_admin_fails_if_not_owner(self, mock_repo_class) -> None:
        mock_repo = mock_repo_class.return_value
        mock_user = type("User", (), {"role": UserRole.ADMIN})()
        mock_repo.get_by_telegram_id.return_value = mock_user

        auth = AuthorizationService(user_repo=mock_repo)
        result = auth.add_admin(123, 456)
        assert "sahip" in result.lower()

    @patch("app.services.authorization.UserRepository")
    def test_remove_admin_fails_if_not_owner(self, mock_repo_class) -> None:
        mock_repo = mock_repo_class.return_value
        mock_user = type("User", (), {"role": UserRole.ADMIN})()
        mock_repo.get_by_telegram_id.return_value = mock_user

        auth = AuthorizationService(user_repo=mock_repo)
        result = auth.remove_admin(123, 456)
        assert "sahip" in result.lower()

    @patch("app.services.authorization.UserRepository")
    def test_register_user_creates_if_not_exists(self, mock_repo_class) -> None:
        mock_repo = mock_repo_class.return_value
        auth = AuthorizationService(user_repo=mock_repo)
        auth.register_user(999)
        mock_repo.upsert.assert_called_once_with(999)
