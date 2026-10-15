from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    """Input schema for public user registration."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=255)
    password: str

    @field_validator("username")
    @classmethod
    def username_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Username must not be blank.")
        return value

    @field_validator("password")
    @classmethod
    def password_length_in_bytes(cls, value: str) -> str:
        password_length = len(value.encode("utf-8"))
        if not 8 <= password_length <= 72:
            raise ValueError("Password must be between 8 and 72 bytes.")
        return value


class UserRead(BaseModel):
    """Public user representation; never includes password data."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    """OAuth2 bearer token response."""

    access_token: str
    token_type: str


class OrderCreate(BaseModel):
    """Request schema for creating a new order."""

    client_name: str = Field(
        min_length=2,
        max_length=120,
        description="Client name.",
    )

    gr_liv_area: float = Field(
        gt=0,
        le=10_000,
        description="Above-ground living area in square feet.",
    )

    total_bsmt_sf: float = Field(
        ge=0,
        le=10_000,
        description="Total basement area in square feet.",
    )

    garage_area: float = Field(
        ge=0,
        le=2_000,
        description="Garage area in square feet.",
    )

    year_built: int = Field(
        ge=1872,
        le=2010,
        description="Original construction year.",
    )

    overall_qual: int = Field(
        ge=1,
        le=10,
        description="Overall material and finish quality, rated from 1 to 10.",
    )

    ms_zoning: str = Field(
        min_length=1,
        max_length=10,
        description="General zoning classification.",
    )


class OrderUpdate(BaseModel):
    """Request schema for updating an existing order.

    All fields are optional; only the fields actually sent by the client
    are updated (partial update / PATCH semantics).
    """

    client_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=120,
        description="Updated client name.",
    )

    gr_liv_area: float | None = Field(
        default=None,
        gt=0,
        le=10_000,
        description="Updated above-ground living area in square feet.",
    )

    total_bsmt_sf: float | None = Field(
        default=None,
        ge=0,
        le=10_000,
        description="Updated total basement area in square feet.",
    )

    garage_area: float | None = Field(
        default=None,
        ge=0,
        le=2_000,
        description="Updated garage area in square feet.",
    )

    year_built: int | None = Field(
        default=None,
        ge=1872,
        le=2010,
        description="Updated original construction year.",
    )

    overall_qual: int | None = Field(
        default=None,
        ge=1,
        le=10,
        description="Updated overall quality rating from 1 to 10.",
    )

    ms_zoning: str | None = Field(
        default=None,
        min_length=1,
        max_length=10,
        description="Updated zoning classification.",
    )


class OrderRead(BaseModel):
    """Response schema representing an order."""

    model_config = {"from_attributes": True}

    id: int
    client_name: str

    gr_liv_area: float
    total_bsmt_sf: float
    garage_area: float
    year_built: int
    overall_qual: int
    ms_zoning: str

    predicted_price: float | None
    created_at: datetime
