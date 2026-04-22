import os

from fastapi import APIRouter, Depends, Header, status, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from exceptions import BaseSecurityError, S3FileUploadError, TokenExpiredError
from schemas.profiles import ProfileResponseSchema, ProfileCreateSchema
from config import get_jwt_auth_manager, get_settings, BaseAppSettings, get_accounts_email_notificator, \
    get_s3_storage_client
from database import get_db, UserModel, UserGroupEnum, UserProfileModel
from security.interfaces import JWTAuthManagerInterface
from storages import S3StorageInterface

router = APIRouter()


def verify_authorization(authorization: str = Header(None)) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing"
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'"
        )
    return token


@router.post(
    "/users/{user_id}/profile/",
    response_model=ProfileResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(
    user_id: int,
    profile_data: ProfileCreateSchema = Depends(),
    db: AsyncSession = Depends(get_db),
    jwt_manager: JWTAuthManagerInterface = Depends(get_jwt_auth_manager),
    s3_client: S3StorageInterface = Depends(get_s3_storage_client),
    token: str = Depends(verify_authorization)
) -> ProfileResponseSchema:

    try:
        decoded_token = jwt_manager.decode_access_token(token)
        token_user_id = decoded_token.get("user_id")
    except TokenExpiredError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired.")
    except BaseSecurityError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    stmt = select(UserModel).where(UserModel.id == user_id).options(
        joinedload(UserModel.profile),
        joinedload(UserModel.group)
    )
    result = await db.execute(stmt)
    user = result.scalars().first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active.",
        )

    stmt_token_user = select(UserModel).where(UserModel.id == token_user_id).options(
        joinedload(UserModel.group)
    )
    result_token_user = await db.execute(stmt_token_user)
    token_user = result_token_user.scalars().first()

    if not token_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or not active."
        )

    if token_user_id != user_id and not token_user.has_group(UserGroupEnum.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to edit this profile."
        )

    if user.profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a profile.",
        )

    extension = os.path.splitext(profile_data.avatar.filename)[1].lower() or ".jpg"
    avatar_key = f"avatars/{user_id}_avatar{extension}"
    avatar_content = await profile_data.avatar.read()
    try:
        await s3_client.upload_file(avatar_key, avatar_content)
    except S3FileUploadError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload avatar. Please try again later."
        )

    new_profile = UserProfileModel(
        user_id=user_id,
        first_name=profile_data.first_name,
        last_name=profile_data.last_name,
        gender=profile_data.gender,
        date_of_birth=profile_data.date_of_birth,
        info=profile_data.info,
        avatar=avatar_key,
    )
    db.add(new_profile)
    await db.flush()
    await db.commit()
    await db.refresh(new_profile)

    avatar_url = await s3_client.get_file_url(avatar_key)
    new_profile.avatar = avatar_url
    return ProfileResponseSchema.model_validate(new_profile)
