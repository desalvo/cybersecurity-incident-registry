def test_user_identity_unique_constraint_is_username_plus_backend():
    from app.models import User

    constraints = list(User.__table__.constraints)
    assert any(
        getattr(constraint, 'name', '') == 'uq_user_username_auth_provider'
        and [column.name for column in constraint.columns] == ['username', 'auth_provider']
        for constraint in constraints
    )
    assert not User.__table__.c.username.unique
