"""Organization data-model tests."""

from sqlalchemy import select

from surgite.auth import create_personal_org, create_user, slugify_org
from surgite.db import OrgMemberRow, OrgRow, get_session


def test_slugify_rules():
    assert slugify_org("alice") == "alice"
    assert slugify_org("Alice.Smith") == "alice-smith"
    assert slugify_org("a+b@weird") == "a-b-weird"
    # Too short is padded to >= 3 chars; empty falls back to "org".
    assert slugify_org("a") == "a-org"
    assert slugify_org("!!") == "org"
    # Trimmed to 32 chars, no leading/trailing dashes.
    assert slugify_org("x" * 50) == "x" * 32
    assert len(slugify_org("x" * 50)) <= 32


def test_create_user_gets_personal_org():
    with get_session() as s:
        user = create_user(s, email="dana@example.com", password="pw-correct-horse")
        assert user.personal_org_id is not None
        org = s.get(OrgRow, user.personal_org_id)
        assert org is not None and org.slug == "dana"
        member = s.get(OrgMemberRow, (org.id, user.id))
        assert member is not None and member.role == "owner"


def test_create_personal_org_is_idempotent():
    with get_session() as s:
        user = create_user(s, email="e@example.com", password="pw-correct-horse")
        first = user.personal_org_id
        again = create_personal_org(s, user)  # already has one -> no new org
        assert again.id == first
        assert s.scalar(select(OrgMemberRow).where(OrgMemberRow.user_id == user.id)) is not None
        assert len(s.scalars(select(OrgRow).where(OrgRow.slug.like("e%"))).all()) == 1


def test_personal_org_slug_disambiguated_on_collision():
    with get_session() as s:
        u1 = create_user(s, email="sam@a.example.com", password="pw-correct-horse")
        u2 = create_user(s, email="sam@b.example.com", password="pw-correct-horse")
        o1 = s.get(OrgRow, u1.personal_org_id)
        o2 = s.get(OrgRow, u2.personal_org_id)
        assert {o1.slug, o2.slug} == {"sam", "sam-2"}
