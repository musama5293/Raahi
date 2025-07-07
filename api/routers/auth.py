from fastapi import APIRouter, HTTPException, Depends

# Import schemas and services
from schemas.user_schema import UserCreate, UserInfo
from services.firebase_service import create_user_in_firebase
from core.security import get_current_user

# TODO: Import UserLogin, Token, and login service

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    responses={404: {"description": "Not found"}},
)

@router.post("/signup", response_model=UserInfo)
async def signup(user: UserCreate):
    """Signs up a new user."""
    try:
        new_user = create_user_in_firebase(user.email, user.password, user.full_name)
        return new_user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")


@router.get("/me", response_model=UserInfo)
async def read_users_me(current_user: dict = Depends(get_current_user)):
    """
    Get the profile of the currently authenticated user.
    """
    # The `get_current_user` dependency already verified the token.
    # The `current_user` object contains the decoded token payload.
    return UserInfo(
        uid=current_user['uid'],
        email=current_user.get('email'),
        full_name=current_user.get('name')
    )

# @router.post("/login", response_model=None) # Replace None with Token
# async def login(form_data: None): # Replace None with UserLogin
#     """Logs in a user and returns a JWT token."""
#     # TODO: Implement user login logic
#     # try:
#     #     token = login_user_in_firebase(form_data.email, form_data.password)
#     #     return {"access_token": token, "token_type": "bearer"}
#     # except Exception as e:
#     #     raise HTTPException(status_code=401, detail="Incorrect email or password")
#     return {"message": "Login endpoint not implemented yet."} 