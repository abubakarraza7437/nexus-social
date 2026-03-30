"""
Test Factories — factory_boy model factories.
Used across all test modules to create realistic test fixtures.
"""

from django.contrib.auth import get_user_model

import factory
import factory.fuzzy

from apps.organizations.models import Organization, OrganizationMember

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Faker("name")
    is_active = True
    is_email_verified = True
    password = factory.PostGenerationMethodCall("set_password", "TestPass123!")


class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization

    name = factory.Faker("company")
    slug = factory.Sequence(lambda n: f"org-{n}")
    plan = Organization.Plan.FREE
    is_active = True


class OrganizationMemberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OrganizationMember

    organization = factory.SubFactory(OrganizationFactory)
    user = factory.SubFactory(UserFactory)
    role = OrganizationMember.Role.EDITOR
    is_active = True
