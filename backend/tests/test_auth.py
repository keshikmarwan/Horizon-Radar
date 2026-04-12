from fastapi import HTTPException

from app.core.auth import get_current_user_id


def test_get_current_user_id_ok():
    assert get_current_user_id('user@example.com') == 'user@example.com'


def test_get_current_user_id_missing_raises():
    try:
        get_current_user_id(None)
        assert False, 'Expected HTTPException'
    except HTTPException as exc:
        assert exc.status_code == 401
