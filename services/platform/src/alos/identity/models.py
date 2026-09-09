from enum import StrEnum


class DivisionCode(StrEnum):
    FINANCE = "FINANCE"
    SALES_MARKETING = "SALES_MARKETING"
    PROPERTY = "PROPERTY"
    HR = "HR"
    LEGAL = "LEGAL"
    IT = "IT"


class HumanRole(StrEnum):
    DIRECTOR = "DIRECTOR"
    DIVISION_LEAD = "DIVISION_LEAD"
    DIVISION_MEMBER = "DIVISION_MEMBER"
    IT_ADMIN = "IT_ADMIN"
    AI_ADMIN = "AI_ADMIN"
    # Legacy values remain readable while existing deployments migrate assignments.
    DIVISION_OWNER = "DIVISION_OWNER"
    IT_LEAD = "IT_LEAD"
    TECHNICAL_REVIEWER = "TECHNICAL_REVIEWER"
    BUSINESS_REVIEWER = "BUSINESS_REVIEWER"
    QA_SECURITY = "QA_SECURITY"


class DataScope(StrEnum):
    COMPANY = "COMPANY"
    DIVISION = "DIVISION"
    PROJECT = "PROJECT"
    OWN_ASSIGNED = "OWN_ASSIGNED"


class SystemActor(StrEnum):
    GENESIS = "GENESIS"
