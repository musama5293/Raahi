from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from firebase_admin import auth

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login") # tokenUrl is not directly used, but required by FastAPI

def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Dependency to verify Firebase ID token and get user data.
    This will be used to protect endpoints.
    """
    try:
        # Verify the token
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token['uid']
        return decoded_token
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) 