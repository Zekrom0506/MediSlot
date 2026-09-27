from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession, limit_login_attempts
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserResponse
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: DbSession) -> TokenResponse:
    """Patients sign themselves up and are logged in straight away."""
    user = auth_service.register_patient(db, request)
    return auth_service.issue_tokens(user)


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(limit_login_attempts)])
def login(request: LoginRequest, db: DbSession) -> TokenResponse:
    """Log in with email and password."""
    return auth_service.login(db, request.email, request.password)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: RefreshRequest, db: DbSession) -> TokenResponse:
    """Get a new access token using a refresh token."""
    return auth_service.refresh_tokens(db, request.refresh_token)


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: CurrentUser) -> UserResponse:
    """Return the logged-in user's profile."""
    return UserResponse.model_validate(current_user)
