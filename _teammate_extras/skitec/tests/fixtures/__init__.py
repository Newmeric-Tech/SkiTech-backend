"""
Test Fixtures Module

Factory functions and fixtures for test data creation.
"""

from datetime import date
from factory import Factory, Faker

from app.models.user import User
from app.models.property import Property
from app.models.workforce import WorkforceEntry


class UserFactory(Factory):
    """Factory for creating test User objects"""

    class Meta:
        model = User

    email = Faker("email")
    username = Faker("user_name")
    first_name = Faker("first_name")
    last_name = Faker("last_name")
    hashed_password = "hashed_test_password"
    is_active = True


class PropertyFactory(Factory):
    """Factory for creating test Property objects"""

    class Meta:
        model = Property

    name = Faker("company")
    code = Faker("bothify", text="PROP-####")
    address = Faker("address")
    city = Faker("city")
    country = Faker("country")
    contact_email = Faker("email")
    is_active = True
    number_of_rooms = 100


class WorkforceFactory(Factory):
    """Factory for creating test WorkforceEntry objects"""

    class Meta:
        model = WorkforceEntry

    first_name = Faker("first_name")
    last_name = Faker("last_name")
    employee_id = Faker("bothify", text="EMP-#####")
    position = Faker("job")
    department = "Operations"
    property_id = 1
    start_date = Faker("date_object")
    end_date = None
    scheduled_hours_per_week = 40
    is_active = True
